#!/usr/bin/env python3
"""M1: cl_tagger batch → image_tags source=auto_tagger."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

_cfg_path = ROOT / "config" / "model_stack_pilot.yaml"
_early_cfg = yaml.safe_load(_cfg_path.read_text(encoding="utf-8")) if _cfg_path.is_file() else {}
from siftivex.gpu_env import apply_tagger_gpu_config  # noqa: E402

apply_tagger_gpu_config(_early_cfg.get("tagger") or {})

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, PILOT_MODEL_CACHE  # noqa: E402
from siftivex.search_index import upsert_image_search  # noqa: E402
from siftivex.tag_stack_migrate import apply_tag_stack_migrations  # noqa: E402
from siftivex.tags_db import replace_auto_tagger_tags  # noqa: E402
from siftivex.vlm import is_readable_image  # noqa: E402


def load_tagger_config(path: Path) -> dict[str, Any]:
    if path.is_file():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def tag_names_from_result(raw: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tag = item.get("tag") if isinstance(item, dict) else str(item)
        if not isinstance(tag, str):
            continue
        tag = tag.strip()
        if tag and tag not in seen:
            seen.add(tag)
            names.append(tag)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cl_tagger on images missing auto_tagger")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "model_stack_pilot.yaml")
    parser.add_argument("--route", type=str, default=None, help="Filter images.route_tag")
    parser.add_argument("--limit", type=int, default=0, help="Max images (0=all pending)")
    parser.add_argument("--commit-every", type=int, default=25)
    parser.add_argument("--retag", action="store_true", help="Overwrite existing auto_tagger")
    parser.add_argument("--download-models", action="store_true")
    args = parser.parse_args()

    applied = apply_tag_stack_migrations(args.db)
    if applied:
        print(f"DB migrate: {applied}", file=sys.stderr)

    cfg = load_tagger_config(args.config)
    t_cfg = cfg.get("tagger") or {}

    try:
        from siftivex.pilot.tagger_cl import ClTaggerSession
    except ImportError as exc:
        print(f"Install pilot extras: uv pip install -e '.[pilot]' ({exc})", file=sys.stderr)
        return 1

    cache = Path(t_cfg.get("cache_dir", PILOT_MODEL_CACHE / "cl_tagger"))
    cuda_id = t_cfg.get("cuda_device_id")
    session = ClTaggerSession(
        cache_dir=cache,
        repo_id=t_cfg.get("repo_id", "cella110n/cl_tagger"),
        gen_threshold=float(t_cfg.get("general_threshold", 0.35)),
        char_threshold=float(t_cfg.get("character_threshold", 0.85)),
        max_tags=int(t_cfg.get("max_tags", 64)),
        download=args.download_models,
        cuda_device_id=int(cuda_id) if cuda_id is not None else None,
    )
    print(f"tagger provider={session.provider} cuda_device_id={cuda_id}", file=sys.stderr)

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
            WHERE t.image_id = i.image_id AND t.source = 'auto_tagger'
          )
        """
    query += " ORDER BY i.image_id"

    conn = get_connection(args.db)
    rows = conn.execute(query, params).fetchall()
    if args.limit > 0:
        rows = rows[: args.limit]

    if not rows:
        print("No images to tag.")
        conn.close()
        return 0

    ok = skip = err = 0
    try:
        for i, row in enumerate(rows, start=1):
            image_id = row["image_id"]
            path = Path(row["source_path"])
            if not is_readable_image(path):
                skip += 1
                print(f"skip\t{image_id}\tunreadable", file=sys.stderr)
                continue
            try:
                raw = session.tag_path(path)
                names = tag_names_from_result(raw)
                replace_auto_tagger_tags(conn, image_id, names)
                upsert_image_search(conn, image_id)
                ok += 1
                print(f"ok\t{image_id}\t{len(names)} tags\t{path.name}")
            except Exception as exc:  # noqa: BLE001
                err += 1
                print(f"err\t{image_id}\t{exc}", file=sys.stderr)

            if args.commit_every > 0 and i % args.commit_every == 0:
                conn.commit()
                print(f"... committed {i}/{len(rows)}", file=sys.stderr)
        conn.commit()
    finally:
        conn.close()

    print(f"Tagged {ok}, skipped {skip}, errors {err}, total {len(rows)}")
    return 1 if err and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
