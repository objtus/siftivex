"""Manual tag patch tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.ingest import ingest_file
from siftivex.tag_edits import TagEditError, apply_tag_patch
from siftivex.tags_db import effective_tags, replace_tags


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


def test_remove_hides_tagger_keeps_row(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    replace_tags(conn, iid, "auto_tagger", ["serafuku"])
    conn.commit()
    apply_tag_patch(conn, iid, remove=["serafuku"])
    conn.commit()
    assert effective_tags(conn, iid) == []
    row = conn.execute(
        "SELECT source FROM image_tags WHERE image_id = ? AND tag = 'serafuku'",
        (iid,),
    ).fetchall()
    sources = {r[0] for r in row}
    assert "auto_tagger" in sources
    assert "manual_removed" in sources


def test_add_manual(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    apply_tag_patch(conn, iid, add=["オリジナル"])
    conn.commit()
    assert "オリジナル" in effective_tags(conn, iid)


def test_restore_after_remove(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    replace_tags(conn, iid, "filename", ["制服"])
    conn.commit()
    apply_tag_patch(conn, iid, remove=["制服"])
    conn.commit()
    assert effective_tags(conn, iid) == []
    apply_tag_patch(conn, iid, restore=["制服"])
    conn.commit()
    assert effective_tags(conn, iid) == ["制服"]


def test_remove_manual_only(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    apply_tag_patch(conn, iid, add=["追加"])
    conn.commit()
    apply_tag_patch(conn, iid, remove=["追加"])
    conn.commit()
    assert effective_tags(conn, iid) == []
    n = conn.execute(
        "SELECT COUNT(*) FROM image_tags WHERE image_id = ? AND tag = '追加'",
        (iid,),
    ).fetchone()[0]
    assert n == 0


def test_retag_layer_unchanged_on_remove(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    replace_tags(conn, iid, "auto_tagger", ["1girl"])
    conn.commit()
    apply_tag_patch(conn, iid, remove=["1girl"])
    replace_tags(conn, iid, "auto_tagger", ["1girl", "solo"])
    conn.commit()
    assert effective_tags(conn, iid) == ["solo"]


def test_route_tag_rejected(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    with pytest.raises(TagEditError):
        apply_tag_patch(conn, iid, add=["route/pixiv"])


def test_empty_body_rejected(image_id: tuple[sqlite3.Connection, str]):
    conn, iid = image_id
    with pytest.raises(TagEditError):
        apply_tag_patch(conn, iid)
