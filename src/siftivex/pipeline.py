"""Phase 0 task pipeline orchestrator."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from siftivex.paths import ROOT

TASKS: dict[str, dict[str, str]] = {
    "0.1": {
        "name": "select_sample",
        "script": "scripts/select_phase0_sample.py",
        "description": "検証用データセット manifest 生成",
    },
    "0.2": {
        "name": "init_db",
        "script": "scripts/init_db.py",
        "description": "SQLite スキーマ初期化",
    },
    "0.2b": {
        "name": "import_manifest",
        "script": "scripts/import_manifest.py",
        "description": "manifest → images テーブル投入",
    },
    "0.3": {
        "name": "embed",
        "script": "scripts/embed.py",
        "description": "CLIP embedding 生成",
    },
    "0.4": {
        "name": "search_test",
        "script": "scripts/search_test.py",
        "description": "LanceDB ANN 検索テスト",
    },
    "0.5": {
        "name": "vlm_tag",
        "script": "scripts/vlm_tag.py",
        "description": "VLM タグ付け",
    },
}

DEFAULT_ORDER = ["0.1", "0.2", "0.2b", "0.3", "0.4", "0.5"]


def run_task(task_id: str, extra_args: list[str] | None = None) -> int:
    task = TASKS.get(task_id)
    if not task:
        print(f"Unknown task: {task_id}", file=sys.stderr)
        return 1

    script = ROOT / task["script"]
    if not script.exists():
        print(f"Script not found: {script}", file=sys.stderr)
        return 1

    cmd = [sys.executable, str(script), *(extra_args or [])]
    print(f"\n=== Task {task_id}: {task['description']} ===")
    print(f"$ {' '.join(cmd)}")
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Siftivex Phase 0 pipeline")
    parser.add_argument(
        "tasks",
        nargs="*",
        help=f"Task IDs to run (default: all). Available: {', '.join(TASKS)}",
    )
    parser.add_argument("--list", action="store_true", help="List tasks and exit")
    args = parser.parse_args(argv)

    if args.list:
        for tid in DEFAULT_ORDER:
            t = TASKS[tid]
            print(f"{tid:5}  {t['name']:16}  {t['description']}")
        return 0

    task_ids = args.tasks or DEFAULT_ORDER
    for tid in task_ids:
        code = run_task(tid)
        if code != 0:
            print(f"Task {tid} failed with exit code {code}", file=sys.stderr)
            return code

    print("\nPipeline finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
