#!/usr/bin/env python3
"""Pick 10 integration story examples from pilot JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tagger", type=Path, default=ROOT / "data/phase0/results/model_stack_pilot_tagger_m300.json")
    parser.add_argument("--d1", type=Path, default=ROOT / "data/phase0/results/model_stack_pilot_d1_g50_gpu.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/plans/pilot_integration_stories.json")
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()

    tagger_rows = {
        r["source_path"]: r
        for r in json.loads(args.tagger.read_text(encoding="utf-8")).get("per_image") or []
        if r.get("tagger_tags")
    }
    d1_by_path = {r["source_path"]: r.get("d1") for r in json.loads(args.d1.read_text(encoding="utf-8")).get("per_image") or []}

    stories = []
    for sp, row in tagger_rows.items():
        top = row["tagger_tags"][:8]
        d1_block = d1_by_path.get(sp)
        d1_ans = (d1_block or {}).get("answers") if isinstance(d1_block, dict) else None
        ns_pick = {}
        if d1_ans:
            ns_pick = {k: v.get("choice") for k, v in d1_ans.items() if k.startswith("ns_") and isinstance(v, dict)}
        general = [t["tag"] for t in top if t.get("category") == "general"][:3]
        stories.append(
            {
                "source_path": sp,
                "filename_hint": Path(sp).name,
                "tagger_top": [t["tag"] for t in top[:5]],
                "d1_namespace": ns_pick or None,
                "embed_query_en_example": ", ".join(general) or top[0]["tag"],
            }
        )
        if len(stories) >= args.count:
            break

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(stories)} stories to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
