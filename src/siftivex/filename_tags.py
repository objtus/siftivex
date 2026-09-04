"""Parse legacy filename-based tags (旧自作アーカイブ形式)."""

from __future__ import annotations

import re
from pathlib import Path

HEX_TOKEN = re.compile(r"^[0-9A-Fa-f]{6,8}$")
NUMERIC_TOKEN = re.compile(r"^\d+$")


def parse_legacy_filename_tags(filename: str) -> list[str]:
    """
    Extract hyphen-separated tags from legacy filenames.

    Examples:
        IMG3078_2D-背景-空.JPG       -> ['2D', '背景', '空']
        IMG_0265-建物-夕方-横.JPG    -> ['建物', '夕方', '横']
        15283_1-風景-山-雲.jpg       -> ['風景', '山', '雲']
    """
    stem = Path(filename).stem
    if "_" not in stem:
        return []

    _, tail = stem.rsplit("_", 1)
    if not tail:
        return []

    tags: list[str] = []
    for token in tail.split("-"):
        token = token.strip()
        if not token:
            continue
        if NUMERIC_TOKEN.fullmatch(token):
            continue
        if HEX_TOKEN.fullmatch(token):
            continue
        tags.append(token)
    return tags
