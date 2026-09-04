#!/usr/bin/env python3
"""Apply Phase 1 schema migrations to an existing or fresh database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection, init_db, migrate_phase1  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Siftivex DB to Phase 1 schema")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Initialize Phase 0 base schema first (no-op if images table exists)",
    )
    args = parser.parse_args()

    if args.fresh or not args.db.exists():
        init_db(args.db)
        print(f"Phase 0 base schema ensured: {args.db}")

    applied = migrate_phase1(args.db)
    if applied:
        print(f"Phase 1 migration applied: {args.db}")
    else:
        print(f"Phase 1 already applied: {args.db}")

    conn = get_connection(args.db)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"
            )
        }
        for name in ("image_metadata", "index_jobs", "image_search", "schema_migrations"):
            status = "ok" if name in tables else "MISSING"
            print(f"  {name}: {status}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
