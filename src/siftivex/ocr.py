"""Dedicated OCR engines for ingest (folder_rules ocr_engine routing)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

OCR_ENGINES = frozenset({"skip", "manga", "paddle"})


def ocr_engine_available(engine: str) -> bool:
    if engine in ("", "skip"):
        return True
    if engine == "manga":
        try:
            import manga_ocr  # noqa: F401
        except ImportError:
            return False
        return True
    if engine == "paddle":
        try:
            from paddleocr import PaddleOCR  # noqa: F401
        except ImportError:
            return False
        return paddle_ocr_usable()
    raise ValueError(f"Unknown OCR engine: {engine!r}")


def run_ocr(path: Path, engine: str) -> str:
    """Run dedicated OCR. skip returns empty string."""
    if not engine or engine == "skip":
        return ""
    if not supports_ocr(path):
        return ""

    if engine == "manga":
        return _run_manga(path)
    if engine == "paddle":
        return _run_paddle(path)
    raise ValueError(f"Unknown OCR engine: {engine!r}")


def supports_ocr(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


@lru_cache(maxsize=1)
def _manga_instance():
    from manga_ocr import MangaOcr

    return MangaOcr()


_paddle_disabled = False


def paddle_ocr_usable() -> bool:
    """False after a runtime failure (e.g. oneDNN incompatibility on this host)."""
    return not _paddle_disabled


@lru_cache(maxsize=1)
def _paddle_instance():
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import PaddleOCR

    return PaddleOCR(lang="japan")


def _run_manga(path: Path) -> str:
    return (_manga_instance()(str(path)) or "").strip()


def _extract_paddle_lines(result) -> list[str]:
    lines: list[str] = []
    for page in result or []:
        if isinstance(page, dict):
            texts = page.get("rec_texts") or page.get("rec_text") or []
            if isinstance(texts, str):
                lines.append(texts)
            else:
                lines.extend(str(t) for t in texts if t)
            continue
        for line in page or []:
            if line and len(line) > 1 and line[1]:
                lines.append(str(line[1][0]))
    return lines


def _run_paddle(path: Path) -> str:
    global _paddle_disabled
    if _paddle_disabled:
        raise RuntimeError("PaddleOCR disabled after prior runtime failure")
    ocr = _paddle_instance()
    try:
        if hasattr(ocr, "predict"):
            result = ocr.predict(str(path))
        else:
            result = ocr.ocr(str(path), cls=True)
    except Exception:
        _paddle_disabled = True
        raise
    return "\n".join(_extract_paddle_lines(result)).strip()
