"""FTS5 search index tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.ingest import ingest_file
from siftivex.search_index import upsert_image_search
from siftivex.tags_db import replace_tags


def test_upsert_image_search_includes_tags_and_ocr(tmp_path: Path):
    db = tmp_path / "test.db"
    init_db(db)
    migrate_phase1(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")

    img = tmp_path / "x.png"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(img)
    result = ingest_file(img, conn, skip_thumbnails=True, skip_ocr=True)
    replace_tags(conn, result.image_id, "filename", ["tag_alpha", "tag_beta"])
    conn.execute(
        "INSERT INTO image_ocr (image_id, auto_ocr) VALUES (?, ?)",
        (result.image_id, "hello world"),
    )
    upsert_image_search(conn, result.image_id)
    conn.commit()

    hits = conn.execute(
        "SELECT tags, ocr_text FROM image_search WHERE image_id = ?",
        (result.image_id,),
    ).fetchone()
    assert "tag_alpha" in hits[0]
    assert hits[1] == "hello world"
    conn.close()
