#!/usr/bin/env python3
"""Summarize tagger tag frequencies and overlap with DB auto tags."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, PHASE0_RESULTS  # noqa: E402
from siftivex.tags_db import tags_grouped_by_source  # noqa: E402


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze tagger_cl pilot output")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    freq: Counter[str] = Counter()
    jaccards: list[float] = []
    conn = get_connection(args.db)
    try:
        for row in report.get("per_image") or []:
            tags = row.get("tagger_tags") or []
            for t in tags:
                if isinstance(t, dict):
                    freq[t.get("tag", "")] += 1
            tag_set = {t["tag"] for t in tags if isinstance(t, dict)}
            iid = row.get("image_id")
            if not iid and row.get("source_path"):
                r = conn.execute(
                    "SELECT image_id FROM images WHERE source_path = ?",
                    (row["source_path"],),
                ).fetchone()
                iid = r["image_id"] if r else None
            if iid:
                auto = set(tags_grouped_by_source(conn, iid)["auto"])
                jaccards.append(jaccard(tag_set, auto))
    finally:
        conn.close()

    out_obj = {
        "tag_frequency_top50": freq.most_common(50),
        "jaccard_tagger_vs_vlm_auto": {
            "mean": round(sum(jaccards) / len(jaccards), 4) if jaccards else None,
            "n": len(jaccards),
        },
    }
    out = args.output or PHASE0_RESULTS / "pilot_tagger_analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out_obj, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
