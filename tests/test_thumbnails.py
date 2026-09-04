"""Thumbnail generation tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from siftivex.thumbnails import (
    PREVIEW_MAX_EDGE,
    THUMB_MAX_EDGE,
    generate_thumbnails,
    resize_max_edge,
)


def test_resize_no_upscale():
    img = Image.new("RGB", (100, 50), (255, 0, 0))
    out = resize_max_edge(img, THUMB_MAX_EDGE)
    assert out.size == (100, 50)


def test_resize_downscales():
    img = Image.new("RGB", (2000, 1000), (0, 255, 0))
    out = resize_max_edge(img, PREVIEW_MAX_EDGE)
    assert max(out.size) == PREVIEW_MAX_EDGE


def test_generate_thumbnails(tmp_path: Path):
    src = tmp_path / "big.png"
    Image.new("RGB", (3000, 2000), (0, 0, 255)).save(src)

    out = generate_thumbnails(src, "img_test123", root=tmp_path / "thumbs")
    assert out.thumb.exists()
    assert out.preview.exists()

    with Image.open(out.thumb) as thumb:
        assert max(thumb.size) == THUMB_MAX_EDGE
    with Image.open(out.preview) as preview:
        assert max(preview.size) == PREVIEW_MAX_EDGE
