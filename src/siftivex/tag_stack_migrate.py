"""Tag stack DB migrations (index_jobs job types)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from siftivex.paths import DEFAULT_DB_PATH, SCHEMA_DIR


def _image_tags_allows_auto_tagger(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='image_tags'"
    ).fetchone()
    if not row or not row[0]:
        return False
    return "auto_tagger" in row[0]


def migrate_image_tags_sources(conn: sqlite3.Connection) -> bool:
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='image_tags'"
    ).fetchone() is None:
        return False
    if _image_tags_allows_auto_tagger(conn):
        return False
    migration = SCHEMA_DIR / "tag_stack_sources.sql"
    if not migration.is_file():
        raise FileNotFoundError(migration)
    conn.executescript(migration.read_text(encoding="utf-8"))
    return True


def _index_jobs_allows_tagger(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='index_jobs'"
    ).fetchone()
    if not row or not row[0]:
        return False
    return "tagger_tag" in row[0]


def migrate_index_jobs_tagger(conn: sqlite3.Connection) -> bool:
    """Add tagger_tag to index_jobs CHECK. Returns True if migration ran."""
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='index_jobs'"
    ).fetchone() is None:
        return False
    if _index_jobs_allows_tagger(conn):
        return False

    migration = SCHEMA_DIR / "tag_stack_jobs.sql"
    if not migration.is_file():
        raise FileNotFoundError(migration)
    conn.executescript(migration.read_text(encoding="utf-8"))
    return True


def ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def apply_tag_stack_migrations(db_path: Path | None = None) -> list[str]:
    path = db_path or DEFAULT_DB_PATH
    applied: list[str] = []
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema_migrations_table(conn)
        if migrate_index_jobs_tagger(conn):
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version) VALUES ('tag_stack_jobs')"
            )
            applied.append("tag_stack_jobs")
        if migrate_image_tags_sources(conn):
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version) VALUES ('tag_stack_sources')"
            )
            applied.append("tag_stack_sources")
        conn.commit()
    finally:
        conn.close()
    return applied
