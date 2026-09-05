"""Tests for incremental sync helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.ingest import ingest_file
from siftivex.sync import collect_changed_paths, mark_missing_for_route


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    init_db(db)
    migrate_phase1(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), (1, 2, 3)).save(path)


def test_collect_changed_paths_new_and_mtime(db_conn: sqlite3.Connection, tmp_path: Path):
    root = tmp_path / "archive"
    img = root / "a.png"
    write_png(img)

    assert collect_changed_paths(root, db_conn) == [img]

    ingest_file(img, db_conn, skip_ocr=True)
    db_conn.commit()
    assert collect_changed_paths(root, db_conn) == []

    img.touch()
    assert collect_changed_paths(root, db_conn) == [img]


def test_mark_missing_for_route(db_conn: sqlite3.Connection, tmp_path: Path):
    img = tmp_path / "gone.png"
    write_png(img)
    ingest_file(img, db_conn, skip_ocr=True)
    db_conn.execute("UPDATE images SET route_tag = 'route/test'")
    db_conn.commit()
    img.unlink()

    n = mark_missing_for_route(db_conn, "route/test")
    assert n == 1
    status = db_conn.execute("SELECT status FROM images").fetchone()[0]
    assert status == "missing"
