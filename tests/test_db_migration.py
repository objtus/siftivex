"""Database migration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from siftivex.db import init_db, migrate_phase1


def test_migrate_phase1_creates_tables(tmp_path: Path):
    db = tmp_path / "test.db"
    init_db(db)
    assert migrate_phase1(db) is True
    assert migrate_phase1(db) is False

    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"
            )
        }
        assert "image_metadata" in tables
        assert "index_jobs" in tables
        assert "image_search" in tables
        assert "schema_migrations" in tables
        row = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = 'phase1'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()
