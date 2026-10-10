"""Tag read/write and effective_tags tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.ingest import ingest_file
from siftivex.tags_db import effective_tags, replace_tags, replace_vlm_tags


@pytest.fixture
def image_id(tmp_path: Path) -> tuple[sqlite3.Connection, str]:
    db = tmp_path / "test.db"
    init_db(db)
    migrate_phase1(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    img = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(img)
    result = ingest_file(img, conn, skip_thumbnails=True, skip_ocr=True)
    conn.commit()
    yield conn, result.image_id
    conn.close()


def test_effective_tags_dedupes_cross_source(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    replace_tags(conn, iid, "filename", ["制服", "透け"])
    replace_tags(conn, iid, "auto", ["制服", "乳首"])
    assert effective_tags(conn, iid) == ["乳首", "制服", "透け"]


def test_effective_tags_dedupes_namespace_flat(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    replace_vlm_tags(
        conn,
        iid,
        {"種類/": "写真"},
        ["写真", "街撮り"],
    )
    assert effective_tags(conn, iid) == ["種類/写真", "街撮り"]


def test_effective_tags_respects_manual_removed(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    replace_tags(conn, iid, "filename", ["制服"])
    replace_tags(conn, iid, "auto", ["透け"])
    replace_tags(conn, iid, "manual_removed", ["透け"])
    replace_tags(conn, iid, "manual_added", ["追加"])
    assert effective_tags(conn, iid) == ["制服", "追加"]


def test_tags_grouped_by_source(image_id: tuple[sqlite3.Connection, str]):
    from siftivex.tags_db import tags_grouped_by_source

    conn, iid = image_id
    replace_tags(conn, iid, "filename", ["制服", "透け"])
    replace_tags(conn, iid, "auto", ["制服", "乳首"])
    replace_tags(conn, iid, "manual_added", ["追加"])
    grouped = tags_grouped_by_source(conn, iid)
    assert grouped["filename"] == ["制服", "透け"]
    assert grouped["auto"] == ["乳首", "制服"]
    assert grouped["manual_added"] == ["追加"]
    assert grouped["effective"] == ["乳首", "制服", "追加", "透け"]
