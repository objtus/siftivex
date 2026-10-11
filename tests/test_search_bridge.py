"""Search with tag bridge OR groups."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.ingest import ingest_file
from siftivex.search import parse_query, search_by_tags
from siftivex.tag_bridge import TagBridgeEntry, TagBridgeMember, empty_tag_bridge, load_tag_bridge, save_tag_bridge
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


def _bridge_file(tmp_path: Path) -> Path:
    path = tmp_path / "tag_bridge.json"
    doc = empty_tag_bridge()
    doc.entries.append(
        TagBridgeEntry(
            label="制服",
            members=[
                TagBridgeMember(source="filename", tag="制服"),
                TagBridgeMember(source="auto_tagger", tag="serafuku"),
            ],
        )
    )
    save_tag_bridge(path, doc)
    return path


def test_bridge_or_search(db_conn: sqlite3.Connection, tmp_path: Path):
    bridge_path = _bridge_file(tmp_path)
    bridge = load_tag_bridge(bridge_path)

    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    c = tmp_path / "c.png"
    write_png(a, (1, 0, 0))
    write_png(b, (0, 1, 0))
    write_png(c, (0, 0, 1))
    ra = ingest_file(a, db_conn, route_tag="route/a", skip_ocr=True)
    rb = ingest_file(b, db_conn, route_tag="route/a", skip_ocr=True)
    rc = ingest_file(c, db_conn, route_tag="route/a", skip_ocr=True)
    replace_tags(db_conn, ra.image_id, "filename", ["制服"])
    replace_tags(db_conn, rb.image_id, "auto_tagger", ["serafuku"])
    replace_tags(db_conn, rc.image_id, "auto_tagger", ["1girl"])
    db_conn.commit()

    hit = search_by_tags(db_conn, parse_query("tag:制服"), bridge=bridge)
    assert hit.total == 2
    ids = {h.image_id for h in hit.items}
    assert ra.image_id in ids
    assert rb.image_id in ids

    only_en = search_by_tags(db_conn, parse_query("tag:serafuku"), bridge=bridge)
    assert only_en.total == 1
    assert only_en.items[0].image_id == rb.image_id

    strict_en = search_by_tags(db_conn, parse_query("tag:=serafuku"), bridge=bridge)
    assert strict_en.total == 1
    assert strict_en.items[0].image_id == rb.image_id

    strict_label = search_by_tags(db_conn, parse_query("tag:=制服"), bridge=bridge)
    assert strict_label.total == 1
    assert strict_label.items[0].image_id == ra.image_id
