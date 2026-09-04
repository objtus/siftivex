#!/usr/bin/env python3
"""Task 0.4: LanceDB ANN search test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.embeddings import Embedder, EmbeddingStore  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, DEFAULT_LANCE_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Test natural language search")
    parser.add_argument("--lance", type=Path, default=DEFAULT_LANCE_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--query", default="anime girl with blue hair")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    store = EmbeddingStore(args.lance)
    embedder = Embedder()
    query_vector = embedder.embed_text(args.query)
    hits = store.search(query_vector, limit=args.limit)

    if not hits:
        print("No results. Run task 0.3 first.", file=sys.stderr)
        return 1

    conn = get_connection(args.db)
    print(f'Query: "{args.query}"\n')
    for rank, (image_id, distance) in enumerate(hits, 1):
        row = conn.execute(
            "SELECT file_name, source_path FROM images WHERE image_id = ?",
            (image_id,),
        ).fetchone()
        name = row["file_name"] if row else "?"
        path = row["source_path"] if row else "?"
        print(f"{rank:2}. {image_id}  cos_dist={distance:.4f}  {name}")
        print(f"    {path}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
