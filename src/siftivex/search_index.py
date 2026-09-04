"""SQLite FTS5 index maintenance."""

from __future__ import annotations

import sqlite3

from siftivex.tags_db import effective_tags


def effective_ocr_text(conn: sqlite3.Connection, image_id: str) -> str:
    row = conn.execute(
        """
        SELECT COALESCE(manual_ocr, auto_ocr, '')
        FROM image_ocr
        WHERE image_id = ?
        """,
        (image_id,),
    ).fetchone()
    return row[0] if row else ""


def upsert_image_search(conn: sqlite3.Connection, image_id: str) -> None:
    tags = " ".join(effective_tags(conn, image_id))
    ocr_text = effective_ocr_text(conn, image_id)
    conn.execute("DELETE FROM image_search WHERE image_id = ?", (image_id,))
    conn.execute(
        "INSERT INTO image_search (image_id, tags, ocr_text) VALUES (?, ?, ?)",
        (image_id, tags, ocr_text),
    )
