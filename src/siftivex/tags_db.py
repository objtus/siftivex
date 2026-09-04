"""Tag read/write helpers."""

from __future__ import annotations

import sqlite3

from siftivex.filename_tags import parse_legacy_filename_tags
from siftivex.tag_vocabulary import load_tag_vocabulary, normalize_tags


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


def effective_tags(conn: sqlite3.Connection, image_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT tag FROM image_tags
        WHERE image_id = ?
          AND source IN ('auto', 'filename', 'manual_added')
          AND tag NOT IN (
            SELECT tag FROM image_tags
            WHERE image_id = ? AND source = 'manual_removed'
          )
        ORDER BY tag
        """,
        (image_id, image_id),
    ).fetchall()
    return [r[0] for r in rows]
