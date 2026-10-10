#!/usr/bin/env python3
"""Export G30 / G50-d1 gold sets for model stack pilot."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, PHASE0_GOLD, PHASE0_MANIFEST  # noqa: E402
from siftivex.tag_vocabulary import parse_namespace_tag  # noqa: E402
from siftivex.tags_db import effective_tags, tags_grouped_by_source  # noqa: E402


def load_manifest_paths(manifest: Path) -> list[str]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    return [e["source_path"] for e in entries if e.get("source_path")]


def lookup_by_path(conn, paths: list[str]) -> list[dict]:
    out: list[dict] = []
    for sp in paths:
        row = conn.execute(
            """
            SELECT image_id, source_path, file_name, vlm_caption
            FROM images WHERE source_path = ? AND status = 'active'
            """,
            (sp,),
        ).fetchone()
        if row is None:
            continue
        iid = row["image_id"]
        grouped = tags_grouped_by_source(conn, iid)
        ns_tags = [t for t in grouped["auto"] if parse_namespace_tag(t)]
        out.append(
            {
                "image_id": iid,
                "source_path": row["source_path"],
                "file_name": row["file_name"],
                "vlm_caption": row["vlm_caption"],
                "tags_effective": effective_tags(conn, iid),
                "tags_auto": grouped["auto"],
                "tags_filename": grouped["filename"],
                "namespace_auto": ns_tags,
            }
        )
    return out


def sample_g30(items: list[dict], n: int, seed: int) -> list[dict]:
    if len(items) <= n:
        return items
    rng = random.Random(seed)
    return rng.sample(items, n)


def filter_g50_d1(items: list[dict]) -> list[dict]:
    """VLM-tagged rows with at least one namespace auto tag (weak labels for d1)."""
    return [it for it in items if it.get("vlm_caption") and it.get("namespace_auto")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export pilot gold sets")
    parser.add_argument("--manifest", type=Path, default=PHASE0_MANIFEST)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--g30", type=int, default=30)
    parser.add_argument("--g50", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=PHASE0_GOLD)
    args = parser.parse_args()

    paths = load_manifest_paths(args.manifest)
    conn = get_connection(args.db)
    try:
        items = lookup_by_path(conn, paths)
    finally:
        conn.close()

    g30 = sample_g30(items, args.g30, args.seed)
    g50_pool = filter_g50_d1(items)
    g50 = sample_g30(g50_pool, min(args.g50, len(g50_pool)), args.seed + 1)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "g30.json").write_text(
        json.dumps({"seed": args.seed, "count": len(g30), "items": g30}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.out_dir / "g50_d1.json").write_text(
        json.dumps(
            {"seed": args.seed + 1, "count": len(g50), "items": g50, "note": "namespace_auto is weak VLM label"},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"manifest paths matched DB: {len(items)}/{len(paths)}")
    print(f"Wrote {args.out_dir / 'g30.json'} ({len(g30)} items)")
    print(f"Wrote {args.out_dir / 'g50_d1.json'} ({len(g50)} items, pool={len(g50_pool)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
