#!/usr/bin/env python3
"""Repair pixiv filename tags: replace p0/p1 page stubs with sidecar pixiv_tags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH  # noqa: E402
from siftivex.search_index import upsert_image_search  # noqa: E402
from siftivex.tags_db import apply_pixiv_tags  # noqa: E402

PAGE_TAG = "p[0-9]*"


def load_pixiv_tags(extra_json: str | None) -> list[str]:
    if not extra_json:
        return []
    try:
        data = json.loads(extra_json)
    except json.JSONDecodeError:
        return []
    raw = data.get("pixiv_tags")
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, str) and t.strip()]


def repair_pixiv_tags(conn, *, dry_run: bool = True) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT i.image_id, i.file_name, m.extra_json
        FROM images i
        LEFT JOIN image_metadata m ON m.image_id = i.image_id
        WHERE i.route_tag = 'route/pixiv' AND i.status = 'active'
        ORDER BY i.image_id
        """
    ).fetchall()

    stats = {
        "total": len(rows),
        "with_metadata_tags": 0,
        "cleared_page_only": 0,
        "updated_search": 0,
    }

    for row in rows:
        image_id = row["image_id"]
        pixiv_tags = load_pixiv_tags(row["extra_json"])
        old_tags = [
            r[0]
            for r in conn.execute(
                "SELECT tag FROM image_tags WHERE image_id = ? AND source = 'filename' ORDER BY tag",
                (image_id,),
            ).fetchall()
        ]

        if pixiv_tags:
            if old_tags == pixiv_tags:
                continue
            stats["with_metadata_tags"] += 1
            if not dry_run:
                apply_pixiv_tags(conn, image_id, pixiv_tags)
                upsert_image_search(conn, image_id)
                stats["updated_search"] += 1
            continue

        page_only = old_tags and all(
            t == "p0" or (t.startswith("p") and t[1:].isdigit()) for t in old_tags
        )
        if not page_only:
            continue
        stats["cleared_page_only"] += 1
        if not dry_run:
            conn.execute(
                "DELETE FROM image_tags WHERE image_id = ? AND source = 'filename'",
                (image_id,),
            )
            upsert_image_search(conn, image_id)
            stats["updated_search"] += 1

    if not dry_run:
        conn.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    conn = get_connection(args.db)
    try:
        stats = repair_pixiv_tags(conn, dry_run=not args.apply)
    finally:
        conn.close()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] pixiv tag repair")
    print(f"  total pixiv images: {stats['total']}")
    print(f"  restore from metadata: {stats['with_metadata_tags']}")
    print(f"  clear page-only tags (no metadata): {stats['cleared_page_only']}")
    if args.apply:
        print(f"  search index updated: {stats['updated_search']}")


if __name__ == "__main__":
    main()
