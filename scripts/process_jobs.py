#!/usr/bin/env python3
"""Process pending index_jobs (OCR, VLM)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.folder_rules import load_folder_rules  # noqa: E402
from siftivex.jobs import run_jobs  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, FOLDER_RULES_PATH  # noqa: E402
from siftivex.vlm import VlmClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Process index_jobs queue")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--folder-rules", type=Path, default=FOLDER_RULES_PATH)
    parser.add_argument(
        "--type",
        choices=["ocr", "vlm_tag", "all"],
        default="all",
        help="Job type to process",
    )
    parser.add_argument("--limit", type=int, default=10, help="Max jobs per run")
    parser.add_argument("--route", type=str, default=None, help="Filter by images.route_tag")
    parser.add_argument("--dry-run", action="store_true", help="List pending jobs only")
    args = parser.parse_args()

    conn = get_connection(args.db)
    job_type = None if args.type == "all" else args.type

    if args.dry_run:
        from siftivex.jobs import fetch_pending_jobs

        jobs = fetch_pending_jobs(
            conn, job_type=job_type, route_tag=args.route, limit=args.limit
        )
        for job in jobs:
            print(f"pending\t{job.job_id}\t{job.job_type}\t{job.image_id}")
        conn.close()
        print(f"{len(jobs)} pending job(s)")
        return 0

    folder_rules = load_folder_rules(args.folder_rules) if args.folder_rules.exists() else None
    vlm_client = None
    if args.type in ("vlm_tag", "all"):
        vlm_client = VlmClient()

    try:
        results = run_jobs(
            conn,
            job_type=job_type,
            route_tag=args.route,
            limit=args.limit,
            folder_rules=folder_rules,
            vlm_client=vlm_client,
        )
    finally:
        conn.close()

    ok = sum(1 for r in results if r.ok)
    fail = len(results) - ok
    for r in results:
        status = "ok" if r.ok else "fail"
        err = f"\t{r.error}" if r.error else ""
        print(f"{status}\t{r.job_type}\t{r.image_id}{err}")

    print(f"Processed {len(results)} job(s): {ok} ok, {fail} failed")
    return 1 if fail and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
