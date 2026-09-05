"""Pixiv work grouping tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.ingest import ingest_file, write_pixiv_metadata
from siftivex.works import get_work_pages, validate_work_id, work_context_for_image


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


def insert_pixiv_page(
    conn: sqlite3.Connection,
    tmp_path: Path,
    *,
    work_id: str,
    page: int,
    title: str = "テスト作品",
) -> str:
    path = tmp_path / f"{work_id}_p{page}.jpg"
    write_png(path, (page * 10, 0, 0))
    result = ingest_file(path, conn, route_tag="route/pixiv", skip_ocr=True)
    write_pixiv_metadata(
        conn,
        result.image_id,
        {
            "work_id": work_id,
            "artist": "test_artist",
            "posted_at": "2024-01-01",
            "title": title,
            "page": page,
            "pixiv_tags": ["R-18", "オリジナル"],
            "source_url": f"https://www.pixiv.net/artworks/{work_id}",
        },
    )
    conn.commit()
    return result.image_id


def test_validate_work_id():
    assert validate_work_id("72456444")
    assert not validate_work_id("abc")
    assert not validate_work_id("72456444_p0")


def test_work_pages_ordered(db_conn: sqlite3.Connection, tmp_path: Path):
    ids = [insert_pixiv_page(db_conn, tmp_path, work_id="9001", page=p) for p in (2, 0, 1)]

    result = get_work_pages(db_conn, "9001")
    assert result is not None
    assert result["page_count"] == 3
    assert [item["page"] for item in result["items"]] == [0, 1, 2]
    assert [item["image_id"] for item in result["items"]] == [ids[1], ids[2], ids[0]]


def test_work_context_navigation(db_conn: sqlite3.Connection, tmp_path: Path):
    ids = [insert_pixiv_page(db_conn, tmp_path, work_id="9002", page=p) for p in range(3)]

    ctx = work_context_for_image(db_conn, ids[1])
    assert ctx is not None
    assert ctx["work_id"] == "9002"
    assert ctx["page"] == 1
    assert ctx["page_index"] == 1
    assert ctx["page_count"] == 3
    assert ctx["prev_image_id"] == ids[0]
    assert ctx["next_image_id"] == ids[2]
    assert ctx["title"] == "テスト作品"


def test_single_page_has_no_work_context(db_conn: sqlite3.Connection, tmp_path: Path):
    image_id = insert_pixiv_page(db_conn, tmp_path, work_id="9003", page=0)
    assert work_context_for_image(db_conn, image_id) is None


def test_work_pages_pagination(db_conn: sqlite3.Connection, tmp_path: Path):
    for page in range(5):
        insert_pixiv_page(db_conn, tmp_path, work_id="9004", page=page)

    page1 = get_work_pages(db_conn, "9004", limit=2, offset=0)
    page2 = get_work_pages(db_conn, "9004", limit=2, offset=2)
    assert page1 is not None and page2 is not None
    assert [item["page"] for item in page1["items"]] == [0, 1]
    assert [item["page"] for item in page2["items"]] == [2, 3]
    assert page1["page_count"] == 5
