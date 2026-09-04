#!/usr/bin/env python3
"""Embed images that have no indexed_at yet (post-ingest batch)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.embeddings import EmbedResult, Embedder, EmbeddingStore  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, DEFAULT_LANCE_PATH  # noqa: E402
from siftivex.vlm import is_readable_image  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CLIP embed pending images")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--lance", type=Path, default=DEFAULT_LANCE_PATH)
    parser.add_argument("--route", type=str, default=None, help="Filter by route_tag")
    parser.add_argument("--limit", type=int, default=0, help="Max images (0=all)")
    parser.add_argument("--commit-every", type=int, default=50)
    args = parser.parse_args()

    query = """
        SELECT image_id, source_path FROM images
        WHERE status = 'active' AND indexed_at IS NULL
    """
    params: list = []
    if args.route:
        query += " AND route_tag = ?"
        params.append(args.route)
    query += " ORDER BY image_id"

    conn = get_connection(args.db)
    rows = conn.execute(query, params).fetchall()
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("No pending images to embed.")
        conn.close()
        return 0

    embedder = Embedder()
    store = EmbeddingStore(args.lance)
    ok = skip = 0

    try:
        for i, row in enumerate(rows, start=1):
            image_id = row["image_id"]
            path = Path(row["source_path"])
            if not is_readable_image(path):
                skip += 1
                print(f"skip\t{image_id}\tunreadable", file=sys.stderr)
                continue

            vector = embedder.embed_image(path)
            store.upsert([EmbedResult(image_id=image_id, vector=vector, model=embedder.model_label)])
            conn.execute(
                """
                UPDATE images
                SET indexed_at = datetime('now'), updated_at = datetime('now')
                WHERE image_id = ?
                """,
                (image_id,),
            )
            ok += 1
            print(f"ok\t{image_id}\t{path.name}")

            if args.commit_every > 0 and i % args.commit_every == 0:
                conn.commit()
                print(f"... committed {i}/{len(rows)}", file=sys.stderr)
        conn.commit()
    finally:
        conn.close()

    print(f"Embedded {ok}, skipped {skip}, total {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
