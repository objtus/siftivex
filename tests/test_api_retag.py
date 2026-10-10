"""POST /api/images/{id}/retag tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import siftivex.api.app as api_app_module
from siftivex.api.app import app
from siftivex.db import init_db, migrate_phase1
from siftivex.ingest import ingest_file
from siftivex.vlm import VlmTagResult


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    db = tmp_path / "test.db"
    init_db(db)
    migrate_phase1(db)
    monkeypatch.setattr(api_app_module, "DEFAULT_DB_PATH", db)
    return TestClient(app)


def test_retag_image_endpoint_updates_tags(api_client: TestClient, tmp_path: Path):
    img = tmp_path / "a.png"
    Image.new("RGB", (8, 8), (10, 20, 30)).save(img)
    conn = sqlite3.connect(api_app_module.DEFAULT_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    result = ingest_file(img, conn, skip_thumbnails=True, skip_ocr=True)
    conn.commit()
    conn.close()

    mock_client = MagicMock()
    mock_client.config = {"enable_thinking": True}
    mock_client.tag_image.return_value = VlmTagResult(
        namespace_tags={"種類/": "写真", "画角/": "全身"},
        flat_tags=["制服", "透け"],
        caption="テストキャプション",
        ocr_text="",
        raw={},
        reasoning_content="短い推論",
    )

    with patch.object(api_app_module, "_vlm_client", lambda: mock_client):
        res = api_client.post(f"/api/images/{result.image_id}/retag")

    assert res.status_code == 200
    data = res.json()
    assert data["image_id"] == result.image_id
    assert "種類/写真" in data["tags"]
    assert "制服" in data["tags"]
    assert data["vlm_caption"] == "テストキャプション"
    assert data["thinking_enabled"] is True
    assert data["reasoning_chars"] == 4
    assert "tag_sources" in data
    assert "制服" in data["tag_sources"]["auto"]
    assert data["prompt_revision"]


def test_retag_image_endpoint_not_found(api_client: TestClient):
    res = api_client.post("/api/images/img_missing/retag")
    assert res.status_code == 404


def test_list_images_include_tag_with_spaces(api_client: TestClient, tmp_path: Path):
    img = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(img)
    db = api_app_module.DEFAULT_DB_PATH
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    ing = ingest_file(img, conn, route_tag="route/a", skip_ocr=True)
    from siftivex.tags_db import replace_auto_tagger_tags

    replace_auto_tagger_tags(conn, ing.image_id, ["bare legs", "1girl"])
    conn.commit()
    conn.close()

    res = api_client.get(
        "/api/images",
        params={"include_tag": "bare legs", "route_tag": "route/a", "limit": 10},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["query"]["include_tags"] == ["bare legs"]
