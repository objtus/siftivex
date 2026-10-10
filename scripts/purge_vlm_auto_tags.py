#!/usr/bin/env python3
"""M0: Remove VLM auto tags and pending vlm_tag jobs (see docs/plans/tag-stack-migration.md)."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DATA_DIR, DEFAULT_DB_PATH  # noqa: E402
from siftivex.tag_stack_migrate import apply_tag_stack_migrations  # noqa: E402


def counts(conn) -> dict[str, int]:
    auto_rows = conn.execute(
        "SELECT COUNT(*) FROM image_tags WHERE source='auto'"
    ).fetchone()[0]
    auto_images = conn.execute(
        "SELECT COUNT(DISTINCT image_id) FROM image_tags WHERE source='auto'"
    ).fetchone()[0]
    vlm_pending = conn.execute(
        "SELECT COUNT(*) FROM index_jobs WHERE job_type='vlm_tag' AND status='pending'"
    ).fetchone()[0]
    vlm_all = conn.execute(
        "SELECT COUNT(*) FROM index_jobs WHERE job_type='vlm_tag'"
    ).fetchone()[0]
    return {
        "auto_tag_rows": auto_rows,
        "auto_images": auto_images,
        "vlm_pending": vlm_pending,
        "vlm_jobs_total": vlm_all,
    }


def backup_db(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = backup_dir / f"siftivex-pre-m0-{stamp}.db"
    shutil.copy2(db_path, dest)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.is_file():
            shutil.copy2(side, backup_dir / f"{dest.name}{suffix}")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge VLM source=auto tags and vlm_tag queue")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Print counts only")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete auto tags and vlm_tag jobs (requires --backup unless --no-backup)",
    )
    parser.add_argument("--backup", action="store_true", help="Copy DB to data/backups/ before apply")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup (dangerous)")
    parser.add_argument(
        "--migrate-jobs",
        action="store_true",
        help="Apply tag_stack index_jobs migration (tagger_tag type)",
    )
    args = parser.parse_args()

    if not args.db.is_file():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    if args.migrate_jobs:
        applied = apply_tag_stack_migrations(args.db)
        print(f"migrate: {applied or 'already up to date'}")

    conn = get_connection(args.db)
    try:
        before = counts(conn)
        print("before:", before)

        if args.dry_run and not args.apply:
            return 0

        if not args.apply:
            print("Use --dry-run or --apply (see --help)", file=sys.stderr)
            return 1

        if not args.no_backup and not args.backup:
            print("Refusing --apply without --backup (or pass --no-backup)", file=sys.stderr)
            return 1

        if args.backup:
            dest = backup_db(args.db, DATA_DIR / "backups")
            print(f"backup: {dest}")

        applied = apply_tag_stack_migrations(args.db)
        if applied:
            print(f"migrate: {applied}")

        conn.execute("DELETE FROM image_tags WHERE source = 'auto'")
        conn.execute("DELETE FROM index_jobs WHERE job_type = 'vlm_tag'")
        conn.commit()
        after = counts(conn)
        print("after:", after)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
