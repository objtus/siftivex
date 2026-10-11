"""d1 state hints from filename (legacy) tags."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.d1_namespace import filename_hint_state
from siftivex.ingest import ingest_file
from siftivex.tags_db import apply_filename_tags, apply_pixiv_tags


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    init_db(db)
    migrate_phase1(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    path = tmp_path / "IMG4239_毛-うんこ.JPG"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(path)
    ing = ingest_file(path, conn, route_tag="route/under-iphone", skip_ocr=True)
    apply_filename_tags(conn, ing.image_id, path.name)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def image_id(db_conn: sqlite3.Connection) -> str:
    row = db_conn.execute("SELECT image_id FROM images LIMIT 1").fetchone()
    return row[0]


def test_filename_hint_state_uses_legacy_order(db_conn: sqlite3.Connection, image_id: str):
    state = filename_hint_state(db_conn, image_id, limit=0)
    assert state is not None
    assert state.startswith("filename tags:")
    assert "毛" in state and "うんこ" in state
    assert state.index("毛") < state.index("うんこ")


def test_filename_hint_state_limit_zero_is_all_tags(db_conn: sqlite3.Connection, image_id: str):
    state = filename_hint_state(db_conn, image_id, limit=0)
    assert state is not None
    assert "毛" in state and "うんこ" in state


def test_filename_hint_state_disabled(db_conn: sqlite3.Connection, image_id: str):
    assert filename_hint_state(db_conn, image_id, limit=-1) is None


def test_pixiv_filename_tags_not_passed_to_d1(db_conn: sqlite3.Connection, tmp_path: Path):
    path = tmp_path / "20240101_12345678_user_title_オリジナル.jpg"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(path)
    ing = ingest_file(path, db_conn, route_tag="route/pixiv", skip_ocr=True)
    apply_pixiv_tags(
        db_conn,
        ing.image_id,
        ["SF", "なにこれ切ない", "オリジナル", "オリジナル10000users入り"],
    )
    db_conn.commit()
    assert filename_hint_state(db_conn, ing.image_id, limit=0, file_name=path.name) is None
