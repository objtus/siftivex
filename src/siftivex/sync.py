"""Incremental sync helpers for n8n / scheduled ingest."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from siftivex.ingest import collect_image_paths, iso_mtime

ARCHIVE_KEYS = ("under_iphone", "pixiv_bookmarks")


def collect_changed_paths(
    root: Path,
    conn: sqlite3.Connection,
    *,
    limit: int = 0,
) -> list[Path]:
    """Paths under root that are new or have an updated mtime vs DB."""
    pending: list[Path] = []
    for path in collect_image_paths(root):
        resolved = str(path.resolve())
        row = conn.execute(
            "SELECT file_mtime, status FROM images WHERE source_path = ?",
            (resolved,),
        ).fetchone()
        if row is None:
            pending.append(path)
        elif row[1] == "missing" or row[0] != iso_mtime(path):
            pending.append(path)
        if limit > 0 and len(pending) >= limit:
            break
    return pending


def mark_missing_for_route(conn: sqlite3.Connection, route_tag: str) -> int:
    """Mark active DB rows missing when source_path no longer exists."""
    rows = conn.execute(
        """
        SELECT image_id, source_path FROM images
        WHERE route_tag = ? AND status = 'active'
        """,
        (route_tag,),
    ).fetchall()
    n = 0
    for row in rows:
        if not Path(row[1]).is_file():
            conn.execute(
                """
                UPDATE images
                SET status = 'missing', updated_at = datetime('now')
                WHERE image_id = ?
                """,
                (row[0],),
            )
            n += 1
    return n
