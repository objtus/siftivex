#!/usr/bin/env python3
"""M2: LiquidAI d1-3B namespace batch → image_tags source=auto_d1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_cfg_path = ROOT / "config" / "model_stack_pilot.yaml"
_early = yaml.safe_load(_cfg_path.read_text(encoding="utf-8")) if _cfg_path.is_file() else {}
from siftivex.gpu_env import apply_d1_gpu_config  # noqa: E402

apply_d1_gpu_config(_early.get("d1") or {})

from siftivex.d1_namespace import (  # noqa: E402
    d1_state_text_from_config,
    is_under_legacy_filename_for_d1,
    namespace_tags_from_d1,
)
from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH  # noqa: E402
from siftivex.pilot.d1_questions import build_d1_question_set  # noqa: E402
from siftivex.pilot.d1_runner import D1Runner  # noqa: E402
from siftivex.search_index import upsert_image_search  # noqa: E402
from siftivex.tag_stack_migrate import apply_tag_stack_migrations  # noqa: E402
from siftivex.tags_db import replace_auto_d1_namespace  # noqa: E402
from siftivex.vlm import is_readable_image  # noqa: E402


def load_config(path: Path) -> dict[str, Any]:
    if path.is_file():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="d1 namespace batch (auto_d1)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--config", type=Path, default=_cfg_path)
    parser.add_argument("--route", type=str, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--commit-every", type=int, default=10)
    parser.add_argument("--retag", action="store_true", help="Overwrite existing auto_d1")
    parser.add_argument(
        "--require-legacy-filename",
        action="store_true",
        help="Only images with under-style filename tags (ID_tag-tag.ext)",
    )
    parser.add_argument(
        "--no-require-filename",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-require-tagger",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    apply_tag_stack_migrations(args.db)

    cfg = load_config(args.config)
    d1_cfg = cfg.get("d1") or {}
    min_prob = float(d1_cfg.get("min_choice_prob", 0.4))
    hint_source = str(d1_cfg.get("state_hint_source", "filename")).strip().lower()

    try:
        runner = D1Runner(
            model_id=d1_cfg.get("model_id", "LiquidAI/d1-3B"),
            prefer_cuda=bool(d1_cfg.get("prefer_cuda", True)),
            device=d1_cfg.get("device"),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"d1 load failed: {exc}", file=sys.stderr)
        print("Install pilot extras: uv pip install -e '.[pilot]'", file=sys.stderr)
        return 1

    questions = build_d1_question_set(cfg, include_namespace=True)
    print(
        f"d1 device={runner._device} questions={len(questions)} min_prob={min_prob} "
        f"state_hint_source={hint_source}",
        file=sys.stderr,
    )

    query = """
        SELECT i.image_id, i.source_path
        FROM images i
        WHERE i.status = 'active'
    """
    params: list = []
    if args.route:
        query += " AND i.route_tag = ?"
        params.append(args.route)
    if not args.retag:
        query += """
          AND NOT EXISTS (
            SELECT 1 FROM image_tags t
            WHERE t.image_id = i.image_id AND t.source = 'auto_d1'
          )
        """
    query += " ORDER BY i.image_id"

    conn = get_connection(args.db)
    rows = conn.execute(query, params).fetchall()
    if args.limit > 0:
        rows = rows[: args.limit]

    if not rows:
        print("No images for d1 batch.")
        conn.close()
        return 0

    ok = skip = err = 0
    try:
        for i, row in enumerate(rows, start=1):
            image_id = row["image_id"]
            path = Path(row["source_path"])
            if not is_readable_image(path):
                skip += 1
                continue
            if args.require_legacy_filename and not is_under_legacy_filename_for_d1(path.name):
                skip += 1
                continue
            try:
                state = d1_state_text_from_config(
                    conn,
                    image_id,
                    d1_cfg,
                    file_name=Path(row["source_path"]).name,
                )
                out = runner.decide(path, questions, state_text=state)
                ns_tags = namespace_tags_from_d1(out, min_choice_prob=min_prob)
                replace_auto_d1_namespace(conn, image_id, ns_tags)
                upsert_image_search(conn, image_id)
                ok += 1
                flat = ", ".join(f"{k}{v}" for k, v in sorted(ns_tags.items()))
                print(f"ok\t{image_id}\t{flat}\t{path.name}")
            except Exception as exc:  # noqa: BLE001
                err += 1
                print(f"err\t{image_id}\t{exc}", file=sys.stderr)

            if args.commit_every > 0 and i % args.commit_every == 0:
                conn.commit()
                print(f"... committed {i}/{len(rows)}", file=sys.stderr)
        conn.commit()
    finally:
        conn.close()

    print(f"d1 done ok={ok} skip={skip} err={err} total={len(rows)}")
    return 1 if err and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
