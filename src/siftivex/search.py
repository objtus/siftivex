"""Image search: query parsing, tag filter, CLIP ANN."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from siftivex.embeddings import Embedder, EmbeddingStore
from siftivex.tags_db import effective_tags

TAG_TOKEN = re.compile(r"^-?tag:(.+)$", re.IGNORECASE)


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


def parse_query(raw: str) -> ParsedQuery:
    parsed = ParsedQuery()
    text_parts: list[str] = []
    for token in raw.split():
        m = TAG_TOKEN.match(token)
        if not m:
            text_parts.append(token)
            continue
        tag = m.group(1).strip()
        if not tag:
            continue
        if token.startswith("-tag:") or token.startswith("-TAG:"):
            parsed.exclude_tags.append(tag)
        else:
            parsed.include_tags.append(tag)
    parsed.text = " ".join(text_parts).strip()
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
                  AND t.source IN ('auto', 'filename', 'manual_added')
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
                  AND t.source IN ('auto', 'filename', 'manual_added')
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
) -> SearchResult:
    parsed = parse_query(query)
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
