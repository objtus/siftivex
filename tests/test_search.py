"""Search query parsing and tag filter tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.ingest import ingest_file
from siftivex.search import parse_query, search_by_tags
from siftivex.tags_db import replace_tags


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    init_db(db)
    migrate_phase1(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def write_png(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color).save(path)


def test_parse_query_tags_and_text():
    q = parse_query("tag:制服 -tag:未分類 青い髪")
    assert q.include_tags == ["制服"]
    assert q.exclude_tags == ["未分類"]
    assert q.text == "青い髪"


def test_search_by_tags_and_route(db_conn: sqlite3.Connection, tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    write_png(a, (1, 0, 0))
    write_png(b, (0, 1, 0))
    ra = ingest_file(a, db_conn, route_tag="route/a", skip_ocr=True)
    rb = ingest_file(b, db_conn, route_tag="route/b", skip_ocr=True)
    replace_tags(db_conn, ra.image_id, "auto", ["制服"])
    replace_tags(db_conn, rb.image_id, "auto", ["制服", "未分類"])
    db_conn.commit()

    result = search_by_tags(
        db_conn,
        parse_query("tag:制服 -tag:未分類"),
        route_tag="route/a",
        limit=10,
    )
    assert result.total == 1
    assert result.items[0].image_id == ra.image_id

    result_b = search_by_tags(db_conn, parse_query("tag:制服"), route_tag="route/b")
    assert result_b.total == 1
    assert result_b.items[0].image_id == rb.image_id
