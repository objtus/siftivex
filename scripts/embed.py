#!/usr/bin/env python3
"""Task 0.3: CLIP embedding generation → LanceDB."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.embeddings import EmbedResult, Embedder, EmbeddingStore  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, DEFAULT_LANCE_PATH, PHASE0_RESULTS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CLIP embeddings")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--lance", type=Path, default=DEFAULT_LANCE_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max images (0=all)")
    args = parser.parse_args()

    conn = get_connection(args.db)
    rows = conn.execute(
        "SELECT image_id, source_path FROM images WHERE status = 'active' ORDER BY image_id"
    ).fetchall()
    conn.close()

    if args.limit > 0:
        rows = rows[: args.limit]

    if not rows:
        print("No images in database. Run task 0.2b first.", file=sys.stderr)
        return 1

    embedder = Embedder()
    store = EmbeddingStore(args.lance)
    results: list[EmbedResult] = []
    timings: list[dict] = []
    skipped: list[dict] = []
    t0 = time.perf_counter()

    for row in rows:
        image_id = row["image_id"]
        path = Path(row["source_path"])
        start = time.perf_counter()
        try:
            vector = embedder.embed_image(path)
        except Exception as exc:
            skipped.append({"image_id": image_id, "path": str(path), "error": str(exc)})
            print(f"  SKIP {image_id}: {exc}", file=sys.stderr)
            continue
        elapsed = time.perf_counter() - start
        results.append(EmbedResult(image_id=image_id, vector=vector, model=embedder.model_label))
        timings.append({"image_id": image_id, "seconds": round(elapsed, 4)})
        print(f"  embedded {image_id} ({elapsed:.2f}s)")

    written = store.upsert(results)
    total = time.perf_counter() - t0

    PHASE0_RESULTS.mkdir(parents=True, exist_ok=True)
    report = {
        "task": "0.3_embed",
        "model": embedder.model_label,
        "device": embedder.device,
        "count": written,
        "skipped": len(skipped),
        "skipped_details": skipped,
        "total_seconds": round(total, 2),
        "avg_seconds": round(total / max(written, 1), 4),
        "per_image": timings,
    }
    report_path = PHASE0_RESULTS / "embed_timing.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {written} embeddings to {args.lance}")
    if skipped:
        print(f"Skipped {len(skipped)} unreadable files")
    print(f"Avg {report['avg_seconds']}s/image, total {report['total_seconds']}s")
    print(f"Timing report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
