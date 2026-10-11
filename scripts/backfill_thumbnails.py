#!/usr/bin/env python3
"""Generate missing thumb.webp / preview.webp for active images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, DEFAULT_THUMBNAILS_DIR  # noqa: E402
from siftivex.thumbnails import generate_thumbnails, supports_thumbnails, thumbnail_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing thumbnails")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--route", type=str, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--commit-every", type=int, default=50)
    args = parser.parse_args()

    query = """
        SELECT image_id, source_path
        FROM images
        WHERE status = 'active'
    """
    params: list = []
    if args.route:
        query += " AND route_tag = ?"
        params.append(args.route)

    conn = get_connection(args.db)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    pending: list[tuple[str, Path]] = []
    for row in rows:
        image_id = row["image_id"]
        thumb = thumbnail_dir(image_id, DEFAULT_THUMBNAILS_DIR) / "thumb.webp"
        if thumb.is_file():
            continue
        pending.append((image_id, Path(row["source_path"])))

    if args.limit > 0:
        pending = pending[: args.limit]

    if not pending:
        print("All active images already have thumbnails.")
        return 0

    ok = skip = err = 0
    for i, (image_id, source) in enumerate(pending, start=1):
        if not source.is_file():
            skip += 1
            print(f"skip\t{image_id}\tmissing source", file=sys.stderr)
            continue
        if not supports_thumbnails(source):
            skip += 1
            print(f"skip\t{image_id}\tunsupported {source.suffix}", file=sys.stderr)
            continue
        try:
            generate_thumbnails(source, image_id)
            ok += 1
            print(f"ok\t{image_id}\t{source.name}")
        except Exception as exc:  # noqa: BLE001
            err += 1
            print(f"err\t{image_id}\t{exc}", file=sys.stderr)

        if args.commit_every > 0 and i % args.commit_every == 0:
            print(f"... {i}/{len(pending)}", file=sys.stderr)

    print(f"Backfill done ok={ok} skip={skip} err={err} pending={len(pending)}")
    return 1 if err and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
