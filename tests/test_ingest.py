"""Ingest worker tests (DB path, no CLIP)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.folder_rules import FolderRule, FolderRules, IngestProfile
from siftivex.ingest import ingest_file, resolve_pixiv_metadata


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    init_db(db)
    migrate_phase1(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def write_png(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color).save(path)


def test_ingest_new_file_registers_and_queues_vlm(db_conn: sqlite3.Connection, tmp_path: Path):
    img = tmp_path / "sample.png"
    write_png(img, (255, 0, 0))

    profile = IngestProfile(name="test", route_tag="route/test")
    rules = FolderRules(
        rules=(FolderRule(path_prefix=tmp_path, profile=profile),),
    )

    result = ingest_file(img, db_conn, folder_rules=rules, skip_ocr=True)
    assert result.is_new is True
    assert result.route_tag == "route/test"
    assert result.vlm_queued is True
    assert result.embedded is False
    assert result.thumbnails_created is True
    assert result.search_indexed is True

    row = db_conn.execute(
        "SELECT route_tag, status FROM images WHERE image_id = ?",
        (result.image_id,),
    ).fetchone()
    assert row == ("route/test", "active")

    jobs = db_conn.execute(
        "SELECT COUNT(*) FROM index_jobs WHERE image_id = ? AND job_type = 'vlm_tag'",
        (result.image_id,),
    ).fetchone()[0]
    assert jobs == 1


def test_ingest_duplicate_updates_path_only(db_conn: sqlite3.Connection, tmp_path: Path):
    img_a = tmp_path / "a.png"
    img_b = tmp_path / "moved" / "b.png"
    write_png(img_a, (0, 128, 255))
    img_b.parent.mkdir(parents=True, exist_ok=True)
    img_b.write_bytes(img_a.read_bytes())

    first = ingest_file(img_a, db_conn, skip_ocr=True)
    second = ingest_file(img_b, db_conn, skip_ocr=True)

    assert first.is_new is True
    assert second.is_new is False
    assert first.image_id == second.image_id
    assert second.vlm_queued is False

    path_row = db_conn.execute(
        "SELECT source_path FROM images WHERE image_id = ?",
        (first.image_id,),
    ).fetchone()[0]
    assert path_row == str(img_b.resolve())

    jobs = db_conn.execute(
        "SELECT COUNT(*) FROM index_jobs WHERE image_id = ?",
        (first.image_id,),
    ).fetchone()[0]
    assert jobs == 1


def test_pixiv_sidecar_metadata(db_conn: sqlite3.Connection, tmp_path: Path):
    img = tmp_path / "4826_p0.jpg"
    write_png(img, (10, 20, 30))
    sidecar = tmp_path / "4826_p0.pixiv.json"
    sidecar.write_text(
        json.dumps(
            {
                "work_id": "4826",
                "artist": "test_artist",
                "posted_at": "2024-01-01",
                "title": "Test",
                "page": 0,
                "pixiv_tags": ["tag1"],
                "source_url": "https://www.pixiv.net/artworks/4826",
            }
        ),
        encoding="utf-8",
    )

    profile = IngestProfile(
        name="pixiv",
        route_tag="route/pixiv",
        metadata="pixiv_hybrid",
    )
    rules = FolderRules(rules=(FolderRule(path_prefix=tmp_path, profile=profile),))

    result = ingest_file(img, db_conn, folder_rules=rules, skip_ocr=True)
    assert result.metadata_written is True

    meta = db_conn.execute(
        "SELECT artist, work_id FROM image_metadata WHERE image_id = ?",
        (result.image_id,),
    ).fetchone()
    assert meta == ("test_artist", "4826")

    tags = db_conn.execute(
        "SELECT tag FROM image_tags WHERE image_id = ? AND source = 'filename' ORDER BY tag",
        (result.image_id,),
    ).fetchall()
    assert [r[0] for r in tags] == ["tag1"]


def test_pixiv_short_filename_does_not_tag_page_number(db_conn: sqlite3.Connection, tmp_path: Path):
    """4826_p0.jpg must not produce filename tag 'p0'."""
    img = tmp_path / "4826_p0.jpg"
    write_png(img, (10, 20, 30))
    sidecar = tmp_path / "4826_p0.pixiv.json"
    sidecar.write_text(
        json.dumps(
            {
                "work_id": "4826",
                "pixiv_tags": ["東方", "博麗霊夢"],
            }
        ),
        encoding="utf-8",
    )

    profile = IngestProfile(name="pixiv", route_tag="route/pixiv", metadata="pixiv_hybrid")
    rules = FolderRules(rules=(FolderRule(path_prefix=tmp_path, profile=profile),))

    ingest_file(img, db_conn, folder_rules=rules, skip_ocr=True)
    tags = [
        r[0]
        for r in db_conn.execute(
            "SELECT tag FROM image_tags WHERE image_id = ? AND source = 'filename' ORDER BY tag",
            (db_conn.execute("SELECT image_id FROM images").fetchone()[0],),
        ).fetchall()
    ]
    assert set(tags) == {"東方", "博麗霊夢"}
    assert "p0" not in tags


def test_ocr_queues_when_engine_unavailable(db_conn: sqlite3.Connection, tmp_path: Path, monkeypatch):
    img = tmp_path / "ocr.png"
    write_png(img, (8, 8, 8))

    profile = IngestProfile(name="pixiv", route_tag="route/pixiv", ocr_engine="manga")
    rules = FolderRules(rules=(FolderRule(path_prefix=tmp_path, profile=profile),))
    monkeypatch.setattr("siftivex.ingest.ocr_engine_available", lambda _engine: False)

    result = ingest_file(img, db_conn, folder_rules=rules, skip_thumbnails=True)
    assert result.ocr_done is False
    assert result.ocr_queued is True

    jobs = db_conn.execute(
        "SELECT job_type FROM index_jobs WHERE image_id = ?",
        (result.image_id,),
    ).fetchall()
    job_types = {row[0] for row in jobs}
    assert "ocr" in job_types
    assert "vlm_tag" in job_types


def test_resolve_pixiv_metadata_prefers_sidecar(tmp_path: Path):
    img = tmp_path / "4826_p0.jpg"
    write_png(img, (1, 2, 3))
    sidecar = tmp_path / "4826_p0.pixiv.json"
    sidecar.write_text('{"work_id": "4826", "artist": "from_sidecar"}', encoding="utf-8")

    meta = resolve_pixiv_metadata(img)
    assert meta is not None
    assert meta["artist"] == "from_sidecar"
