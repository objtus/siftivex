#!/usr/bin/env python3
"""Task 0.5: VLM tagging via llama.cpp (Qwen3.6 35B)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.filename_tags import parse_legacy_filename_tags  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, PHASE0_RESULTS  # noqa: E402
from siftivex.tags_db import apply_filename_tags, effective_tags, replace_vlm_tags  # noqa: E402
from siftivex.vlm import VlmClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="VLM auto-tagging")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max images (0=all)")
    parser.add_argument("--retry-errors", action="store_true", help="Only images without auto tags")
    args = parser.parse_args()

    conn = get_connection(args.db)
    if args.retry_errors:
        query = """
            SELECT i.image_id, i.source_path, i.file_name FROM images i
            WHERE i.status = 'active'
              AND NOT EXISTS (
                SELECT 1 FROM image_tags t
                WHERE t.image_id = i.image_id AND t.source = 'auto'
              )
            ORDER BY i.image_id
        """
    else:
        query = """
            SELECT image_id, source_path, file_name FROM images
            WHERE status = 'active' ORDER BY image_id
        """
    rows = conn.execute(query).fetchall()
    conn.close()

    if args.limit > 0:
        rows = rows[: args.limit]

    if not rows:
        print("No images in database.", file=sys.stderr)
        return 1

    client = VlmClient()
    timings: list[dict] = []
    errors: list[dict] = []
    tagged = 0
    t0 = time.perf_counter()

    conn = get_connection(args.db)
    try:
        for row in rows:
            image_id = row["image_id"]
            path = Path(row["source_path"])
            filename = row["file_name"]

            filename_tags = apply_filename_tags(conn, image_id, filename)
            start = time.perf_counter()
            try:
                result = client.tag_image(path, priority_tags=filename_tags)
                replace_vlm_tags(conn, image_id, result.namespace_tags, result.flat_tags)
                conn.execute(
                    "UPDATE images SET vlm_caption = ?, updated_at = datetime('now') WHERE image_id = ?",
                    (result.caption, image_id),
                )
                if not result.namespace_tags and not result.flat_tags:
                    conn.execute(
                        "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (?, ?, 'auto')",
                        (image_id, "未分類"),
                    )
                conn.commit()
                elapsed = time.perf_counter() - start
                eff = effective_tags(conn, image_id)
                timings.append(
                    {
                        "image_id": image_id,
                        "file_name": filename,
                        "filename_tags": filename_tags,
                        "seconds": round(elapsed, 2),
                        "tag_count": len(eff),
                    }
                )
                tagged += 1
                print(
                    f"  tagged {image_id} ({elapsed:.1f}s) "
                    f"fn={len(filename_tags)} total={len(eff)}"
                )
            except Exception as exc:
                conn.rollback()
                errors.append({"image_id": image_id, "path": str(path), "error": str(exc)})
                print(f"  ERROR {image_id}: {exc}", file=sys.stderr)
    finally:
        conn.close()

    total = time.perf_counter() - t0
    PHASE0_RESULTS.mkdir(parents=True, exist_ok=True)
    report = {
        "task": "0.5_vlm_tag",
        "model": client.model,
        "count": tagged,
        "errors": len(errors),
        "total_seconds": round(total, 2),
        "avg_seconds": round(total / max(tagged, 1), 2),
        "timings": timings,
        "error_details": errors,
    }
    report_path = PHASE0_RESULTS / "vlm_timing.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Tagged {tagged} images, {len(errors)} errors")
    print(f"Avg {report['avg_seconds']}s/image, total {report['total_seconds']}s")
    print(f"Report: {report_path}")
    return 1 if errors and not tagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
