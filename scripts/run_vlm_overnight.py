#!/usr/bin/env python3
"""Run VLM tagging overnight for one route (default: under.iphone only)."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.jobs import fetch_pending_jobs, run_jobs  # noqa: E402
from siftivex.lockfile import LockError, job_lock  # noqa: E402
from siftivex.paths import DATA_DIR, DEFAULT_DB_PATH  # noqa: E402
from siftivex.vlm import VlmClient  # noqa: E402


def log(msg: str, log_path: Path) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Overnight VLM batch for one route")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--route", default="route/under-iphone", help="Only process this route_tag")
    parser.add_argument("--batch-size", type=int, default=10, help="Jobs per batch")
    parser.add_argument("--max-images", type=int, default=0, help="Stop after N images (0=all pending)")
    parser.add_argument("--sleep", type=float, default=2.0, help="Seconds between batches")
    args = parser.parse_args()

    log_path = DATA_DIR / "batch" / "vlm-overnight.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with job_lock("vlm-overnight"):
            client = VlmClient()
            processed = ok_total = fail_total = 0

            log(f"start route={args.route} batch_size={args.batch_size}", log_path)

            while True:
                if args.max_images and processed >= args.max_images:
                    break

                batch_limit = args.batch_size
                if args.max_images:
                    batch_limit = min(batch_limit, args.max_images - processed)

                conn = get_connection(args.db)
                pending = fetch_pending_jobs(
                    conn,
                    job_type="vlm_tag",
                    route_tag=args.route,
                    limit=1,
                )
                if not pending:
                    conn.close()
                    log("no pending jobs", log_path)
                    break
                conn.close()

                conn = get_connection(args.db)
                try:
                    results = run_jobs(
                        conn,
                        job_type="vlm_tag",
                        route_tag=args.route,
                        limit=batch_limit,
                        vlm_client=client,
                    )
                finally:
                    conn.close()

                if not results:
                    break

                ok = sum(1 for r in results if r.ok)
                fail = len(results) - ok
                processed += len(results)
                ok_total += ok
                fail_total += fail
                log(f"batch ok={ok} fail={fail} total={processed}", log_path)

                if args.sleep > 0:
                    time.sleep(args.sleep)

            log(f"done processed={processed} ok={ok_total} fail={fail_total}", log_path)
    except LockError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
