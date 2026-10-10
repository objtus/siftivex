"""Image search: query parsing, tag filter, CLIP ANN."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from siftivex.embeddings import Embedder, EmbeddingStore
from siftivex.tags_db import effective_tags

# Unquoted value is \S+ only; use tag:"black hair" for spaced Danbooru-style tags.
TAG_PATTERN = re.compile(
    r'(-?)tag:(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|(\S+))',
    re.IGNORECASE,
)


@dataclass
class ParsedQuery:
    include_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    text: str = ""


@dataclass
class SearchHit:
    image_id: str
    file_name: str
    route_tag: str | None
    width: int | None
    height: int | None
    score: float | None = None


@dataclass
class SearchResult:
    total: int
    items: list[SearchHit]
    parsed: ParsedQuery


def _unescape_quoted_tag(tag: str) -> str:
    return tag.replace('\\"', '"').replace("\\'", "'").strip()


def merge_parsed_query(
    parsed: ParsedQuery,
    *,
    extra_include: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> ParsedQuery:
    """Combine tag: tokens in q with explicit include_tag / exclude_tag query params."""
    include = list(parsed.include_tags)
    exclude = list(parsed.exclude_tags)
    seen_inc = set(include)
    seen_exc = set(exclude)
    for raw_tag in extra_include or []:
        tag = raw_tag.strip()
        if tag and tag not in seen_inc:
            seen_inc.add(tag)
            include.append(tag)
    for raw_tag in extra_exclude or []:
        tag = raw_tag.strip()
        if tag and tag not in seen_exc:
            seen_exc.add(tag)
            exclude.append(tag)
    return ParsedQuery(include_tags=include, exclude_tags=exclude, text=parsed.text)


def parse_query(raw: str) -> ParsedQuery:
    parsed = ParsedQuery()
    text_parts: list[str] = []
    last = 0
    for m in TAG_PATTERN.finditer(raw):
        text_parts.append(raw[last : m.start()])
        last = m.end()
        tag = _unescape_quoted_tag(m.group(2) or m.group(3) or m.group(4) or "")
        if not tag:
            continue
        if m.group(1) == "-":
            parsed.exclude_tags.append(tag)
        else:
            parsed.include_tags.append(tag)
    text_parts.append(raw[last:])
    parsed.text = " ".join("".join(text_parts).split())
    return parsed


def _tag_filter_clause(
    parsed: ParsedQuery,
    route_tag: str | None,
    *,
    alias: str = "i",
) -> tuple[str, list]:
    clauses = [f"{alias}.status = 'active'"]
    params: list = []
    if route_tag:
        clauses.append(f"{alias}.route_tag = ?")
        params.append(route_tag)
    for tag in parsed.include_tags:
        clauses.append(
            f"""
            EXISTS (
                SELECT 1 FROM image_tags t
                WHERE t.image_id = {alias}.image_id
                  AND t.tag = ?
                  AND t.source IN ('auto', 'filename', 'auto_tagger', 'auto_d1', 'inferred_ja', 'manual_added')
                  AND t.tag NOT IN (
                      SELECT tag FROM image_tags r
                      WHERE r.image_id = {alias}.image_id AND r.source = 'manual_removed'
                  )
            )
            """
        )
        params.append(tag)
    for tag in parsed.exclude_tags:
        clauses.append(
            f"""
            NOT EXISTS (
                SELECT 1 FROM image_tags t
                WHERE t.image_id = {alias}.image_id
                  AND t.tag = ?
                  AND t.source IN ('auto', 'filename', 'auto_tagger', 'auto_d1', 'inferred_ja', 'manual_added')
                  AND t.tag NOT IN (
                      SELECT tag FROM image_tags r
                      WHERE r.image_id = {alias}.image_id AND r.source = 'manual_removed'
                  )
            )
            """
        )
        params.append(tag)
    return " AND ".join(clauses), params


def _rows_to_hits(rows) -> list[SearchHit]:
    return [
        SearchHit(
            image_id=r["image_id"],
            file_name=r["file_name"],
            route_tag=r["route_tag"],
            width=r["width"],
            height=r["height"],
            score=r["score"] if "score" in r.keys() else None,
        )
        for r in rows
    ]


def search_by_tags(
    conn: sqlite3.Connection,
    parsed: ParsedQuery,
    *,
    route_tag: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> SearchResult:
    where, params = _tag_filter_clause(parsed, route_tag)
    total = conn.execute(
        f"SELECT COUNT(*) FROM images i WHERE {where}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT i.image_id, i.file_name, i.route_tag, i.width, i.height
        FROM images i
        WHERE {where}
        ORDER BY i.file_name
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return SearchResult(total=total, items=_rows_to_hits(rows), parsed=parsed)


def search_semantic(
    conn: sqlite3.Connection,
    store: EmbeddingStore,
    embedder: Embedder,
    parsed: ParsedQuery,
    *,
    route_tag: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> SearchResult:
    if not parsed.text:
        return search_by_tags(conn, parsed, route_tag=route_tag, limit=limit, offset=offset)

    vector = embedder.embed_text(parsed.text)
    fetch = min(max(limit + offset, limit) * 20, 2000)
    ann_hits = store.search(vector, limit=fetch)
    if not ann_hits:
        return SearchResult(total=0, items=[], parsed=parsed)

    where, params = _tag_filter_clause(parsed, route_tag)
    id_list = [image_id for image_id, _ in ann_hits]
    placeholders = ", ".join("?" for _ in id_list)
    rows = conn.execute(
        f"""
        SELECT i.image_id, i.file_name, i.route_tag, i.width, i.height
        FROM images i
        WHERE {where} AND i.image_id IN ({placeholders})
        """,
        [*params, *id_list],
    ).fetchall()
    row_map = {r["image_id"]: r for r in rows}
    distance_map = {image_id: dist for image_id, dist in ann_hits}

    ranked: list[SearchHit] = []
    for image_id, distance in ann_hits:
        row = row_map.get(image_id)
        if row is None:
            continue
        ranked.append(
            SearchHit(
                image_id=row["image_id"],
                file_name=row["file_name"],
                route_tag=row["route_tag"],
                width=row["width"],
                height=row["height"],
                score=round(1.0 - distance, 6),
            )
        )

    total = len(ranked)
    page = ranked[offset : offset + limit]
    return SearchResult(total=total, items=page, parsed=parsed)


def search_images(
    conn: sqlite3.Connection,
    query: str,
    *,
    route_tag: str | None = None,
    limit: int = 60,
    offset: int = 0,
    store: EmbeddingStore | None = None,
    embedder: Embedder | None = None,
    extra_include_tags: list[str] | None = None,
    extra_exclude_tags: list[str] | None = None,
) -> SearchResult:
    parsed = merge_parsed_query(
        parse_query(query),
        extra_include=extra_include_tags,
        extra_exclude=extra_exclude_tags,
    )
    if parsed.text and store is not None and embedder is not None:
        return search_semantic(
            conn,
            store,
            embedder,
            parsed,
            route_tag=route_tag,
            limit=limit,
            offset=offset,
        )
    return search_by_tags(conn, parsed, route_tag=route_tag, limit=limit, offset=offset)


def image_to_dict(conn: sqlite3.Connection, hit: SearchHit) -> dict:
    return {
        "image_id": hit.image_id,
        "file_name": hit.file_name,
        "route_tag": hit.route_tag,
        "width": hit.width,
        "height": hit.height,
        "tags": effective_tags(conn, hit.image_id),
        "score": hit.score,
    }
