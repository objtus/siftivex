#!/usr/bin/env python3
"""Lock-protected tasks for n8n / cron scheduled indexing."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.config import archive_server_path, load_paths_config  # noqa: E402
from siftivex.db import get_connection  # noqa: E402
from siftivex.folder_rules import load_folder_rules  # noqa: E402
from siftivex.ingest import ingest_file  # noqa: E402
from siftivex.jobs import run_jobs  # noqa: E402
from siftivex.lockfile import LockError, job_lock  # noqa: E402
from siftivex.paths import DATA_DIR, DEFAULT_DB_PATH, FOLDER_RULES_PATH  # noqa: E402
from siftivex.sync import ARCHIVE_KEYS, collect_changed_paths, mark_missing_for_route  # noqa: E402
from siftivex.vlm import VlmClient  # noqa: E402

ARCHIVE_ROUTES = {
    "under_iphone": "route/under-iphone",
    "pixiv_bookmarks": "route/pixiv",
}

LOG_DIR = DATA_DIR / "batch"


def _log_path(name: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"n8n-{name}.log"


def _append_log(path: Path, line: str) -> None:
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {line}\n")


def run_ingest(archives: list[str], limit: int, skip_ocr: bool) -> int:
    paths_cfg = load_paths_config()
    folder_rules = load_folder_rules(FOLDER_RULES_PATH) if FOLDER_RULES_PATH.exists() else None
    log_path = _log_path("ingest")
    stats = {"new": 0, "dup": 0, "err": 0, "files": 0}

    conn = get_connection(DEFAULT_DB_PATH)
    try:
        for archive in archives:
            root = archive_server_path(archive, paths_cfg)
            pending = collect_changed_paths(root, conn, limit=limit)
            for path in pending:
                stats["files"] += 1
                try:
                    result = ingest_file(
                        path,
                        conn,
                        folder_rules=folder_rules,
                        skip_ocr=skip_ocr,
                    )
                    if result.is_new:
                        stats["new"] += 1
                    else:
                        stats["dup"] += 1
                    conn.commit()
                except Exception as exc:
                    stats["err"] += 1
                    _append_log(log_path, f"err {archive} {path.name} {exc}")
            conn.commit()
    finally:
        conn.close()

    summary = (
        f"ingest archives={','.join(archives)} files={stats['files']} "
        f"new={stats['new']} dup={stats['dup']} err={stats['err']}"
    )
    print(summary)
    _append_log(log_path, summary)
    return 1 if stats["err"] and not stats["new"] else 0


def run_embed(limit: int, route: str | None) -> int:
    cmd = [str(ROOT / ".venv" / "bin" / "python"), "scripts/embed_pending.py"]
    if route:
        cmd.extend(["--route", route])
    if limit > 0:
        cmd.extend(["--limit", str(limit)])
    log_path = _log_path("embed")
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== embed limit={limit} route={route or 'all'} ===\n")
        log.flush()
        proc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print(f"embed exit={proc.returncode} log={log_path}")
    _append_log(log_path, f"embed exit={proc.returncode}")
    return proc.returncode


def run_vlm(limit: int, route: str | None) -> int:
    conn = get_connection(DEFAULT_DB_PATH)
    client = VlmClient()
    try:
        results = run_jobs(
            conn,
            job_type="vlm_tag",
            route_tag=route,
            limit=limit,
            vlm_client=client,
        )
    finally:
        conn.close()

    ok = sum(1 for r in results if r.ok)
    fail = len(results) - ok
    summary = f"vlm route={route or 'all'} ok={ok} fail={fail} total={len(results)}"
    print(summary)
    _append_log(_log_path("vlm"), summary)
    for r in results:
        if not r.ok:
            print(f"fail\t{r.image_id}\t{r.error}", file=sys.stderr)
    return 1 if fail and not ok else 0


def run_mark_missing() -> int:
    conn = get_connection(DEFAULT_DB_PATH)
    try:
        total = 0
        for archive, route in ARCHIVE_ROUTES.items():
            n = mark_missing_for_route(conn, route)
            total += n
            print(f"missing {archive} route={route} marked={n}")
        conn.commit()
    finally:
        conn.close()
    _append_log(_log_path("missing"), f"marked={total}")
    return 0


def run_status() -> int:
    conn = get_connection(DEFAULT_DB_PATH)
    try:
        total = conn.execute("SELECT COUNT(*) FROM images WHERE status='active'").fetchone()[0]
        embedded = conn.execute(
            "SELECT COUNT(*) FROM images WHERE status='active' AND indexed_at IS NOT NULL"
        ).fetchone()[0]
        embed_pending = conn.execute(
            "SELECT COUNT(*) FROM images WHERE status='active' AND indexed_at IS NULL"
        ).fetchone()[0]
        vlm_pending = conn.execute(
            "SELECT COUNT(*) FROM index_jobs WHERE job_type='vlm_tag' AND status='pending'"
        ).fetchone()[0]
        missing = conn.execute("SELECT COUNT(*) FROM images WHERE status='missing'").fetchone()[0]
    finally:
        conn.close()

    payload = {
        "images_active": total,
        "embedded": embedded,
        "embed_pending": embed_pending,
        "vlm_pending": vlm_pending,
        "missing": missing,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="n8n/cron indexing tasks (lock-protected)")
    sub = parser.add_subparsers(dest="task", required=True)

    p_ingest = sub.add_parser("ingest", help="Incremental ingest for changed/new files")
    p_ingest.add_argument(
        "--archive",
        action="append",
        choices=ARCHIVE_KEYS,
        dest="archives",
        help="Repeatable; default: both archives",
    )
    p_ingest.add_argument("--limit", type=int, default=500, help="Max changed files per archive")
    p_ingest.add_argument("--ocr", action="store_true", help="Run dedicated OCR during ingest")

    p_embed = sub.add_parser("embed", help="Embed pending images")
    p_embed.add_argument("--limit", type=int, default=200)
    p_embed.add_argument("--route", default=None)

    p_vlm = sub.add_parser("vlm", help="Process VLM queue")
    p_vlm.add_argument("--limit", type=int, default=5)
    p_vlm.add_argument("--route", default=None)

    sub.add_parser("mark-missing", help="Mark DB rows missing when file gone")
    sub.add_parser("status", help="JSON status for monitoring")

    args = parser.parse_args()
    lock_name = f"n8n-{args.task}"

    try:
        with job_lock(lock_name):
            if args.task == "ingest":
                archives = args.archives or list(ARCHIVE_KEYS)
                return run_ingest(archives, args.limit, skip_ocr=not args.ocr)
            if args.task == "embed":
                return run_embed(args.limit, args.route)
            if args.task == "vlm":
                return run_vlm(args.limit, args.route)
            if args.task == "mark-missing":
                return run_mark_missing()
            if args.task == "status":
                return run_status()
    except LockError as exc:
        print(str(exc), file=sys.stderr)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
