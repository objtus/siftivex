#!/usr/bin/env python3
"""Ingest an archive then embed pending images (sequential, lock-protected)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.config import archive_server_path, load_paths_config  # noqa: E402
from siftivex.lockfile import LockError, job_lock  # noqa: E402
from siftivex.paths import DATA_DIR  # noqa: E402

ARCHIVE_ROUTES = {
    "under_iphone": "route/under-iphone",
    "pixiv_bookmarks": "route/pixiv",
}

PY = ROOT / ".venv" / "bin" / "python"


def run_step(label: str, cmd: list[str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"=== {label} ===", flush=True)
    print(f"log: {log_path}", flush=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== {label} ===\n")
        log.flush()
        proc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print(f"{label}: exit {proc.returncode}", flush=True)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive ingest + embed batch")
    parser.add_argument("--archive", required=True, choices=list(ARCHIVE_ROUTES))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--skip-embed", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true", default=True)
    parser.add_argument("--commit-every", type=int, default=200)
    args = parser.parse_args()

    route = ARCHIVE_ROUTES[args.archive]
    cfg = load_paths_config()
    root = archive_server_path(args.archive, cfg)
    log_dir = DATA_DIR / "batch"
    ingest_log = log_dir / f"ingest-{args.archive}.log"
    embed_log = log_dir / f"embed-{args.archive}.log"

    print(f"archive={args.archive} path={root} route={route}")

    try:
        with job_lock(f"batch-{args.archive}"):
            if not args.skip_ingest:
                cmd = [
                    str(PY),
                    "scripts/ingest.py",
                    "--archive",
                    args.archive,
                    "--commit-every",
                    str(args.commit_every),
                ]
                if args.skip_ocr:
                    cmd.append("--skip-ocr")
                if args.limit > 0:
                    cmd.extend(["--limit", str(args.limit)])
                code = run_step("ingest", cmd, ingest_log)
                if code != 0:
                    return code

            if not args.skip_embed:
                cmd = [
                    str(PY),
                    "scripts/embed_pending.py",
                    "--route",
                    route,
                    "--commit-every",
                    "50",
                ]
                if args.limit > 0:
                    cmd.extend(["--limit", str(args.limit)])
                code = run_step("embed", cmd, embed_log)
                if code != 0:
                    return code
    except LockError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Batch complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
