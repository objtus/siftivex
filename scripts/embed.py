#!/usr/bin/env python3
"""Task 0.3: CLIP embedding generation (stub)."""

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

    print(f"[stub] embed: {count} images ready in {DEFAULT_DB_PATH}")
    print("Install embed extras: pip install -e '.[embed]'")
    print("Implementation pending: open_clip/SigLIP → LanceDB write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
