#!/usr/bin/env python3
"""Task 0.2: Initialize SQLite schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import init_db  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize Siftivex database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    path = init_db(args.db)
    print(f"Database initialized: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
