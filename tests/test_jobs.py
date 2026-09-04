"""index_jobs queue tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from siftivex.db import init_db, migrate_phase1
from siftivex.folder_rules import FolderRule, FolderRules, IngestProfile
from siftivex.ingest import ingest_file, queue_ocr_job, write_auto_ocr
from siftivex.jobs import fetch_pending_jobs, merge_vlm_ocr, process_ocr_job, run_jobs
from siftivex.vlm import VlmTagResult


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    init_db(db)
    migrate_phase1(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (100, 150, 200)).save(path)


def test_fetch_pending_jobs(db_conn: sqlite3.Connection, tmp_path: Path):
    img = tmp_path / "a.png"
    _make_image(img)
    result = ingest_file(img, db_conn, skip_thumbnails=True, skip_ocr=True)
    queue_ocr_job(db_conn, result.image_id)
    db_conn.commit()

    jobs = fetch_pending_jobs(db_conn, job_type="ocr", limit=5)
    assert len(jobs) == 1
    assert jobs[0].image_id == result.image_id


def test_merge_vlm_ocr_skips_when_dedicated_exists(db_conn: sqlite3.Connection, tmp_path: Path):
    img = tmp_path / "b.png"
    _make_image(img)
    result = ingest_file(img, db_conn, skip_thumbnails=True, skip_ocr=True)
    write_auto_ocr(db_conn, result.image_id, "dedicated text")
    merge_vlm_ocr(db_conn, result.image_id, "vlm text")
    db_conn.commit()

    row = db_conn.execute(
        "SELECT auto_ocr FROM image_ocr WHERE image_id = ?",
        (result.image_id,),
    ).fetchone()
    assert row[0] == "dedicated text"


def test_process_ocr_job(db_conn: sqlite3.Connection, tmp_path: Path, monkeypatch):
    img = tmp_path / "c.png"
    _make_image(img)
    result = ingest_file(img, db_conn, skip_thumbnails=True, skip_ocr=True)
    queue_ocr_job(db_conn, result.image_id)
    db_conn.commit()
    jobs = fetch_pending_jobs(db_conn, job_type="ocr", limit=1)
    job = jobs[0]

    profile = IngestProfile(name="t", route_tag="route/t", ocr_engine="skip")
    rules = FolderRules(rules=(FolderRule(path_prefix=tmp_path, profile=profile),))
    monkeypatch.setattr("siftivex.jobs.run_ocr", lambda _path, _engine: "test ocr")

    outcome = process_ocr_job(db_conn, job, folder_rules=rules)
    assert outcome.ok is True

    row = db_conn.execute(
        "SELECT auto_ocr FROM image_ocr WHERE image_id = ?",
        (result.image_id,),
    ).fetchone()
    assert row[0] == "test ocr"


def test_run_jobs_vlm(db_conn: sqlite3.Connection, tmp_path: Path):
    img = tmp_path / "d.png"
    _make_image(img)
    result = ingest_file(img, db_conn, skip_thumbnails=True, skip_ocr=True)
    db_conn.execute(
        "INSERT INTO index_jobs (image_id, job_type, status) VALUES (?, 'vlm_tag', 'pending')",
        (result.image_id,),
    )
    db_conn.commit()

    mock_client = MagicMock()
    mock_client.tag_image.return_value = VlmTagResult(
        namespace_tags={"髪色:": "黒"},
        flat_tags=["test"],
        caption="cap",
        ocr_text="bubble",
        raw={},
    )

    outcomes = run_jobs(db_conn, job_type="vlm_tag", limit=1, vlm_client=mock_client)
    assert len(outcomes) == 1
    assert outcomes[0].ok is True

    status = db_conn.execute(
        "SELECT status FROM index_jobs WHERE image_id = ?",
        (result.image_id,),
    ).fetchone()[0]
    assert status == "done"

    ocr = db_conn.execute(
        "SELECT auto_ocr FROM image_ocr WHERE image_id = ?",
        (result.image_id,),
    ).fetchone()[0]
    assert ocr == "bubble"
