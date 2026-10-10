#!/usr/bin/env python3
"""Compare d1 namespace choices against G50 weak labels (VLM namespace tags)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.paths import PHASE0_GOLD, PHASE0_RESULTS  # noqa: E402
from siftivex.pilot.d1_eval import expected_from_gold, predicted_from_d1  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze d1 vs G50 weak labels")
    parser.add_argument("--report", type=Path, required=True, help="pilot JSON with d1 per_image")
    parser.add_argument("--gold", type=Path, default=PHASE0_GOLD / "g50_d1.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    gold_by_path = {it["source_path"]: it for it in gold.get("items") or []}
    report = json.loads(args.report.read_text(encoding="utf-8"))

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "total": 0, "missing_pred": 0})
    per_image: list[dict] = []

    for row in report.get("per_image") or []:
        sp = row.get("source_path")
        if sp not in gold_by_path:
            continue
        g = gold_by_path[sp]
        exp = expected_from_gold(g)
        pred = predicted_from_d1(row.get("d1"))
        for ns, val in exp.items():
            stats[ns]["total"] += 1
            p = pred.get(ns)
            if p is None:
                stats[ns]["missing_pred"] += 1
            elif p == val:
                stats[ns]["ok"] += 1
        per_image.append({"source_path": sp, "expected": exp, "predicted": pred})

    summary = {ns: {**v, "accuracy": round(v["ok"] / v["total"], 3) if v["total"] else 0} for ns, v in stats.items()}
    out_obj = {"summary": summary, "per_image": per_image}
    out = args.output or PHASE0_RESULTS / "pilot_d1_analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
