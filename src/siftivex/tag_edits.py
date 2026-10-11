"""Manual tag edits via manual_added / manual_removed (see docs/specs/tag-editing.md)."""

from __future__ import annotations

import sqlite3

from siftivex.tags_db import effective_tags

MAX_TAG_LEN = 200
_MACHINE_SOURCES = (
    "auto",
    "filename",
    "auto_tagger",
    "auto_d1",
    "inferred_ja",
)


class TagEditError(ValueError):
    pass


def normalize_manual_tag(raw: str) -> str:
    tag = (raw or "").strip()
    if not tag:
        raise TagEditError("tag must not be empty")
    if len(tag) > MAX_TAG_LEN:
        raise TagEditError(f"tag too long (max {MAX_TAG_LEN})")
    if tag.startswith("route/"):
        raise TagEditError("route tags cannot be edited manually")
    return tag


def _image_exists(conn: sqlite3.Connection, image_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM images WHERE image_id = ? AND status = 'active'",
        (image_id,),
    ).fetchone()
    return row is not None


def _has_machine_tag(conn: sqlite3.Connection, image_id: str, tag: str) -> bool:
    placeholders = ",".join("?" for _ in _MACHINE_SOURCES)
    row = conn.execute(
        f"""
        SELECT 1 FROM image_tags
        WHERE image_id = ? AND tag = ? AND source IN ({placeholders})
        LIMIT 1
        """,
        (image_id, tag, *_MACHINE_SOURCES),
    ).fetchone()
    return row is not None


def _insert_manual(conn: sqlite3.Connection, image_id: str, source: str, tag: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (?, ?, ?)",
        (image_id, tag, source),
    )


def apply_tag_add(conn: sqlite3.Connection, image_id: str, tag: str) -> None:
    t = normalize_manual_tag(tag)
    if t in effective_tags(conn, image_id):
        return
    conn.execute(
        "DELETE FROM image_tags WHERE image_id = ? AND source = 'manual_removed' AND tag = ?",
        (image_id, t),
    )
    if t in effective_tags(conn, image_id):
        return
    _insert_manual(conn, image_id, "manual_added", t)


def apply_tag_remove(conn: sqlite3.Connection, image_id: str, tag: str) -> None:
    t = normalize_manual_tag(tag)
    conn.execute(
        "DELETE FROM image_tags WHERE image_id = ? AND source = 'manual_added' AND tag = ?",
        (image_id, t),
    )
    if _has_machine_tag(conn, image_id, t):
        _insert_manual(conn, image_id, "manual_removed", t)


def apply_tag_restore(conn: sqlite3.Connection, image_id: str, tag: str) -> None:
    t = normalize_manual_tag(tag)
    conn.execute(
        "DELETE FROM image_tags WHERE image_id = ? AND source = 'manual_removed' AND tag = ?",
        (image_id, t),
    )


def apply_tag_patch(
    conn: sqlite3.Connection,
    image_id: str,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    restore: list[str] | None = None,
) -> None:
    if not _image_exists(conn, image_id):
        raise TagEditError("image not found")
    adds = add or []
    removes = remove or []
    restores = restore or []
    if not adds and not removes and not restores:
        raise TagEditError("at least one of add, remove, restore is required")
    for raw in restores:
        apply_tag_restore(conn, image_id, raw)
    for raw in removes:
        apply_tag_remove(conn, image_id, raw)
    for raw in adds:
        apply_tag_add(conn, image_id, raw)
