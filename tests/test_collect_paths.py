"""collect_image_paths tests."""

from pathlib import Path

from PIL import Image

from siftivex.ingest import collect_image_paths


def test_collect_image_paths_case_insensitive(tmp_path: Path):
    Image.new("RGB", (4, 4)).save(tmp_path / "lower.jpg")
    Image.new("RGB", (4, 4)).save(tmp_path / "UPPER.JPG")
    (tmp_path / "skip.txt").write_text("not an image", encoding="utf-8")

    paths = collect_image_paths(tmp_path)
    names = {p.name for p in paths}
    assert names == {"lower.jpg", "UPPER.JPG"}
