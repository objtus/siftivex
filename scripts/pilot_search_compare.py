#!/usr/bin/env python3
"""Compare CLIP vs EmbeddingGemma 2 retrieval on pilot corpus vectors."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.embeddings import Embedder  # noqa: E402
from siftivex.paths import PHASE0_RESULTS  # noqa: E402
from siftivex.pilot.config import load_pilot_config  # noqa: E402

DEFAULT_QUERIES = [
    "制服 透け",
    "水着 屋外",
    "スクショ 会話",
    "街撮り",
    "0人 背景のみ",
    "バストアップ 正面",
    "漫画",
    "イラスト 青髪",
    "anime girl blue hair",
    "school uniform",
]


def cosine_rank(query: list[float], matrix: np.ndarray) -> np.ndarray:
    q = np.asarray(query, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    m = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    return np.argsort(-(m @ q))


def main() -> int:
    parser = argparse.ArgumentParser(description="CLIP vs Gemma2 search on pilot embed cache")
    parser.add_argument("--vectors", type=Path, required=True, help="JSON from pilot with gemma vectors")
    parser.add_argument("--queries-file", type=Path, help="One query per line")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = json.loads(Path(args.vectors).read_text(encoding="utf-8"))
    rows = report.get("per_image") or []
    paths: list[str] = []
    clip_matrix: list[list[float]] = []
    gemma_matrix: list[list[float]] = []
    for row in rows:
        g = row.get("embed_gemma2") or {}
        if not g.get("vector"):
            continue
        ce = row.get("clip_vector")
        if ce is None:
            continue
        paths.append(row["source_path"])
        clip_matrix.append(ce)
        gemma_matrix.append(g["vector"])

    if not paths:
        print("No rows with both clip_vector and embed_gemma2.vector. Re-run pilot with both backends.", file=sys.stderr)
        return 1

    queries = DEFAULT_QUERIES
    if args.queries_file and args.queries_file.is_file():
        queries = [ln.strip() for ln in args.queries_file.read_text(encoding="utf-8").splitlines() if ln.strip()]

    cfg = load_pilot_config()
    eg_cfg = cfg.get("embedding_gemma2") or {}
    try:
        from siftivex.pilot.embed_gemma2 import Gemma2Embedder

        gemma = Gemma2Embedder(model_id=eg_cfg.get("model_id", "google/embeddinggemma-2"))
    except Exception as exc:  # noqa: BLE001
        print(f"Gemma2 unavailable: {exc}", file=sys.stderr)
        return 1

    clip = Embedder()
    clip_m = np.asarray(clip_matrix, dtype=np.float32)
    gemma_m = np.asarray(gemma_matrix, dtype=np.float32)

    results: list[dict] = []
    for q in queries:
        cq = clip.embed_text(q)
        gq = gemma.embed_query(q)
        cr = cosine_rank(cq, clip_m)[: args.top]
        gr = cosine_rank(gq, gemma_m)[: args.top]
        results.append(
            {
                "query": q,
                "clip_top": [paths[i] for i in cr],
                "gemma_top": [paths[i] for i in gr],
            }
        )
        print(f"\n=== {q} ===")
        print("CLIP:", [Path(paths[i]).name for i in cr[:5]])
        print("Gemma:", [Path(paths[i]).name for i in gr[:5]])

    out = args.output
    if out is None:
        PHASE0_RESULTS.mkdir(parents=True, exist_ok=True)
        out = PHASE0_RESULTS / "pilot_search_compare.json"
    out.write_text(json.dumps({"queries": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
