#!/usr/bin/env python3
"""Task 0.5: VLM tagging via llama-swap (stub)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH  # noqa: E402


def main() -> int:
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    finally:
        conn.close()

    print(f"[stub] vlm_tag: {count} images in {DEFAULT_DB_PATH}")
    print("Implementation pending: llama-swap VLM → image_tags (source=auto)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
