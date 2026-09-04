"""Generate thumb/preview WebP thumbnails (no upscale)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

from siftivex.paths import DEFAULT_THUMBNAILS_DIR

THUMB_MAX_EDGE = 256
PREVIEW_MAX_EDGE = 1280
WEBP_QUALITY = 80

RASTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@dataclass(frozen=True)
class ThumbnailPaths:
    thumb: Path
    preview: Path


def thumbnail_dir(image_id: str, root: Path | None = None) -> Path:
    base = root or DEFAULT_THUMBNAILS_DIR
    return base / image_id


def supports_thumbnails(path: Path) -> bool:
    return path.suffix.lower() in RASTER_EXTENSIONS


def _load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as img:
        if getattr(img, "is_animated", False):
            img.seek(0)
        return img.convert("RGB")


def resize_max_edge(img: Image.Image, max_edge: int) -> Image.Image:
    width, height = img.size
    long_edge = max(width, height)
    if long_edge <= max_edge:
        return img.copy()
    scale = max_edge / long_edge
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def generate_thumbnails(
    source: Path,
    image_id: str,
    *,
    root: Path | None = None,
) -> ThumbnailPaths:
    """Write thumb.webp and preview.webp; returns output paths."""
    if not supports_thumbnails(source):
        raise ValueError(f"Thumbnails not supported for {source.suffix}")

    out_dir = thumbnail_dir(image_id, root)
    out_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = out_dir / "thumb.webp"
    preview_path = out_dir / "preview.webp"

    img = _load_rgb(source)
    resize_max_edge(img, THUMB_MAX_EDGE).save(thumb_path, "WEBP", quality=WEBP_QUALITY)
    resize_max_edge(img, PREVIEW_MAX_EDGE).save(preview_path, "WEBP", quality=WEBP_QUALITY)
    return ThumbnailPaths(thumb=thumb_path, preview=preview_path)
