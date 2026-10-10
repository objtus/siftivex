#!/usr/bin/env python3
"""d1-3B ablation: image-only vs tagger hints vs filename hints (G50 weak labels)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.paths import PHASE0_GOLD, PHASE0_RESULTS  # noqa: E402
from siftivex.pilot.config import load_pilot_config  # noqa: E402
from siftivex.pilot.d1_questions import build_d1_question_set  # noqa: E402
from siftivex.pilot.d1_runner import D1Runner  # noqa: E402

from siftivex.pilot.d1_eval import expected_from_gold, predicted_from_d1  # noqa: E402


def load_tagger_by_path(report_path: Path) -> dict[str, list[dict]]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for row in data.get("per_image") or []:
        sp = row.get("source_path")
        if sp and row.get("tagger_tags"):
            out[sp] = row["tagger_tags"]
    return out


def state_for_mode(mode: str, item: dict, tagger_tags: list[dict] | None) -> str | None:
    if mode == "none":
        return None
    if mode == "tagger" and tagger_tags:
        tags = [t["tag"] for t in tagger_tags[:10]]
        return "tagger hints: " + ", ".join(tags)
    if mode == "filename":
        fn = item.get("tags_filename") or []
        if fn:
            return "filename tags: " + ", ".join(fn[:15])
    return None


def accuracy(expected: dict[str, str], predicted: dict[str, str]) -> dict[str, float]:
    stats: dict[str, list[bool]] = defaultdict(list)
    for ns, val in expected.items():
        stats[ns].append(predicted.get(ns) == val)
    return {ns: round(sum(v) / len(v), 3) for ns, v in stats.items() if v}


def main() -> int:
    parser = argparse.ArgumentParser(description="d1 ablation on G50 gold set")
    parser.add_argument("--gold", type=Path, default=PHASE0_GOLD / "g50_d1.json")
    parser.add_argument("--tagger-report", type=Path, default=PHASE0_RESULTS / "model_stack_pilot_tagger_m300.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "model_stack_pilot.yaml")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    items = gold.get("items") or []
    if args.limit > 0:
        items = items[: args.limit]

    tagger_map = load_tagger_by_path(args.tagger_report) if args.tagger_report.is_file() else {}
    cfg = load_pilot_config(args.config)
    questions = build_d1_question_set(cfg, include_namespace=True)
    d1_cfg = cfg.get("d1") or {}
    runner = D1Runner(model_id=d1_cfg.get("model_id", "LiquidAI/d1-3B"), prefer_cuda=bool(d1_cfg.get("prefer_cuda", False)))

    modes = ("none", "tagger", "filename")
    summary: dict[str, dict[str, float]] = {}
    per_image: list[dict] = []

    for mode in modes:
        ns_hits: dict[str, list[bool]] = defaultdict(list)
        t0 = time.perf_counter()
        for item in items:
            sp = item["source_path"]
            path = Path(sp)
            if not path.is_file():
                continue
            state = state_for_mode(mode, item, tagger_map.get(sp))
            out = runner.decide(path, questions, state_text=state)
            pred = predicted_from_d1(out)
            exp = expected_from_gold(item)
            row = {"source_path": sp, "mode": mode, "expected": exp, "predicted": pred, "state": state}
            per_image.append(row)
            for ns, val in exp.items():
                ns_hits[ns].append(pred.get(ns) == val)
        elapsed = time.perf_counter() - t0
        summary[mode] = {
            **{ns: round(sum(v) / len(v), 3) for ns, v in ns_hits.items() if v},
            "_sec": round(elapsed, 2),
            "_n": len(items),
        }
        print(f"{mode}: {elapsed:.1f}s", summary[mode])

    out_obj = {"summary_by_mode": summary, "per_image": per_image}
    out = args.output or PHASE0_RESULTS / "pilot_d1_ablation_g50.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
