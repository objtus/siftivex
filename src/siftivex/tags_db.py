"""Tag read/write helpers."""

from __future__ import annotations

import sqlite3

from siftivex.filename_tags import parse_legacy_filename_tags
from siftivex.tag_vocabulary import dedupe_namespace_flat_tags, load_tag_vocabulary, normalize_tags

RETRY_TAG = "要再タグ"

# Tag stack sources (see docs/specs/tags.md)
SOURCE_AUTO_TAGGER = "auto_tagger"
SOURCE_AUTO_D1 = "auto_d1"
SOURCE_INFERRED_JA = "inferred_ja"

# Effective search / FTS: machine tags (legacy `auto` omitted after M0 purge)
_MACHINE_TAG_SOURCES = (
    "filename",
    SOURCE_AUTO_TAGGER,
    SOURCE_AUTO_D1,
    SOURCE_INFERRED_JA,
    "manual_added",
)


def tags_to_rows(image_id: str, tags: list[str], source: str) -> list[tuple[str, str, str]]:
    seen: set[str] = set()
    rows: list[tuple[str, str, str]] = []
    for tag in tags:
        tag = tag.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        rows.append((image_id, tag, source))
    return rows


def namespace_to_rows(image_id: str, namespace_tags: dict[str, str], source: str) -> list[tuple]:
    rows: list[tuple] = []
    for ns, value in namespace_tags.items():
        rows.append((image_id, f"{ns}{value}", source))
    return rows


def replace_tags(conn: sqlite3.Connection, image_id: str, source: str, tags: list[str]) -> None:
    conn.execute("DELETE FROM image_tags WHERE image_id = ? AND source = ?", (image_id, source))
    for row in tags_to_rows(image_id, tags, source):
        conn.execute(
            "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (?, ?, ?)",
            row,
        )


def replace_vlm_tags(
    conn: sqlite3.Connection,
    image_id: str,
    namespace_tags: dict[str, str],
    flat_tags: list[str],
) -> None:
    conn.execute("DELETE FROM image_tags WHERE image_id = ? AND source = 'auto'", (image_id,))
    for row in namespace_to_rows(image_id, namespace_tags, "auto"):
        conn.execute(
            "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (?, ?, ?)",
            row,
        )
    for row in tags_to_rows(image_id, flat_tags, "auto"):
        conn.execute(
            "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (?, ?, ?)",
            row,
        )


def apply_filename_tags(conn: sqlite3.Connection, image_id: str, filename: str) -> list[str]:
    raw = parse_legacy_filename_tags(filename)
    vocab = load_tag_vocabulary()
    tags = normalize_tags(
        raw,
        aliases=vocab.get("aliases"),
        noise_patterns=vocab.get("noise_patterns"),
    )
    replace_tags(conn, image_id, "filename", tags)
    return tags


def replace_auto_tagger_tags(conn: sqlite3.Connection, image_id: str, tags: list[str]) -> None:
    replace_tags(conn, image_id, SOURCE_AUTO_TAGGER, tags)


def replace_auto_d1_namespace(
    conn: sqlite3.Connection,
    image_id: str,
    namespace_tags: dict[str, str],
) -> None:
    """Replace namespace tags (種類/…形式) under source=auto_d1."""
    conn.execute(
        "DELETE FROM image_tags WHERE image_id = ? AND source = ?",
        (image_id, SOURCE_AUTO_D1),
    )
    for row in namespace_to_rows(image_id, namespace_tags, SOURCE_AUTO_D1):
        conn.execute(
            "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (?, ?, ?)",
            row,
        )


def apply_pixiv_tags(conn: sqlite3.Connection, image_id: str, tags: list[str]) -> list[str]:
    """Apply pixiv downloader tags from sidecar / filename parser."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            continue
        tag = tag.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag)
    replace_tags(conn, image_id, "filename", cleaned)
    return cleaned


def effective_tags(conn: sqlite3.Connection, image_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT tag FROM image_tags
        WHERE image_id = ?
          AND source IN ('auto', 'filename', 'auto_tagger', 'auto_d1', 'inferred_ja', 'manual_added')
          AND tag NOT IN (
            SELECT tag FROM image_tags
            WHERE image_id = ? AND source = 'manual_removed'
          )
        ORDER BY tag
        """,
        (image_id, image_id),
    ).fetchall()
    tags = [r[0] for r in rows]
    return dedupe_namespace_flat_tags(tags)


def tags_grouped_by_source(conn: sqlite3.Connection, image_id: str) -> dict[str, list[str]]:
    """Tags split by source (for UI: distinguish filename vs VLM auto)."""
    removed = {
        r[0]
        for r in conn.execute(
            "SELECT tag FROM image_tags WHERE image_id = ? AND source = 'manual_removed'",
            (image_id,),
        ).fetchall()
    }
    grouped: dict[str, list[str]] = {
        "auto": [],
        "filename": [],
        "auto_tagger": [],
        "auto_d1": [],
        "inferred_ja": [],
        "manual_added": [],
    }
    rows = conn.execute(
        """
        SELECT source, tag FROM image_tags
        WHERE image_id = ?
          AND source IN ('auto', 'filename', 'auto_tagger', 'auto_d1', 'inferred_ja', 'manual_added')
        ORDER BY source, tag
        """,
        (image_id,),
    ).fetchall()
    seen: dict[str, set[str]] = {k: set() for k in grouped}
    for source, tag in rows:
        if tag in removed or tag in seen[source]:
            continue
        seen[source].add(tag)
        grouped[source].append(tag)
    grouped["auto"] = dedupe_namespace_flat_tags(grouped["auto"])
    grouped["manual_removed"] = [
        r[0]
        for r in conn.execute(
            """
            SELECT tag FROM image_tags
            WHERE image_id = ? AND source = 'manual_removed'
            ORDER BY tag
            """,
            (image_id,),
        ).fetchall()
    ]
    grouped["effective"] = effective_tags(conn, image_id)
    return grouped


def mark_vlm_retry_needed(conn: sqlite3.Connection, image_id: str) -> None:
    """Clear auto VLM tags and mark image for re-tagging."""
    replace_vlm_tags(conn, image_id, {}, [RETRY_TAG])
    conn.execute(
        "UPDATE images SET vlm_caption = NULL, updated_at = datetime('now') WHERE image_id = ?",
        (image_id,),
    )


def mark_image_missing(conn: sqlite3.Connection, image_id: str) -> None:
    conn.execute(
        "UPDATE images SET status = 'missing', updated_at = datetime('now') WHERE image_id = ?",
        (image_id,),
    )
