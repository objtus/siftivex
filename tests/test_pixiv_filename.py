import subprocess
import sys
from pathlib import Path

from siftivex.pixiv_filename import parse_pixiv_filename


def test_standalone_script_help():
    script = Path(__file__).resolve().parents[1] / "scripts" / "pixiv_migrate_standalone.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "dry-run" in result.stdout.lower() or "--apply" in result.stdout


def test_parse_pixiv_filename_basic():
    name = "date_2007-09-17id_4826_p0user_artistnametitle_sample-title_tags_風景,空.jpg"
    meta = parse_pixiv_filename(name)
    assert meta is not None
    assert meta.work_id == "4826"
    assert meta.page == 0
    assert meta.artist == "artistname"
    assert meta.title == "sample-title"
    assert meta.pixiv_tags == ["風景", "空"]
    assert meta.short_filename() == "4826_p0.jpg"
    assert meta.sidecar_filename() == "4826_p0.pixiv.json"
    assert "pixiv.net/artworks/4826" in meta.source_url


def test_parse_without_tags_keyword():
    name = (
        "date_2023-08-06id_110577126_p29user_日下氏"
        "title_最近描いたデレマスまとめ_アイドルマスターシンデレラガールズ,久川凪.png"
    )
    meta = parse_pixiv_filename(name)
    assert meta is not None
    assert meta.work_id == "110577126"
    assert meta.page == 29
    assert meta.title == "最近描いたデレマスまとめ"
    assert "久川凪" in meta.pixiv_tags
    assert meta.parse_mode == "no_tags_keyword"


def test_parse_underscore_work_id():
    name = (
        "date_2024-12-06_124937780_p3user_Boob Equality"
        "title_Sling Kanna_AI生成,水着.png"
    )
    meta = parse_pixiv_filename(name)
    assert meta is not None
    assert meta.work_id == "124937780"
    assert meta.page == 3
    assert meta.short_filename() == "124937780_p3.png"


def test_parse_without_page():
    name = "date_2007-09-17id_4826user_artisttitle_hello_tags_tag1.png"
    meta = parse_pixiv_filename(name)
    assert meta is not None
    assert meta.page is None
    assert meta.short_filename() == "4826.png"
