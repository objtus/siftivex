#!/usr/bin/env python3
"""Task 0.4: LanceDB ANN search test (stub)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.paths import DEFAULT_LANCE_PATH  # noqa: E402


def main() -> int:
    print(f"[stub] search_test: LanceDB path {DEFAULT_LANCE_PATH}")
    print("Implementation pending: natural language query → ANN → top-k results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
