#!/usr/bin/env python3
"""Task 0.2b: Import manifest entries into images table."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.ids import content_hash, image_id_from_hash  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, PHASE0_MANIFEST  # noqa: E402


def iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat()


def import_entry(conn, entry: dict) -> str:
    path = Path(entry["source_path"])
    if not path.exists():
        raise FileNotFoundError(path)

    full_hash = content_hash(path)
    image_id = image_id_from_hash(full_hash)
    mime_type, _ = mimetypes.guess_type(path.name)

    width = height = None
    try:
        from PIL import Image

        with Image.open(path) as img:
            width, height = img.size
    except Exception:
        pass

    conn.execute(
        """
        INSERT INTO images (
            image_id, content_hash, source_path, file_name, file_size,
            width, height, mime_type, route_tag, file_mtime
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(content_hash) DO UPDATE SET
            source_path = excluded.source_path,
            file_name   = excluded.file_name,
            file_size   = excluded.file_size,
            width       = excluded.width,
            height      = excluded.height,
            mime_type   = excluded.mime_type,
            route_tag   = excluded.route_tag,
            file_mtime  = excluded.file_mtime,
            status      = 'active',
            updated_at  = datetime('now')
        """,
        (
            image_id,
            full_hash,
            str(path),
            path.name,
            path.stat().st_size,
            width,
            height,
            mime_type,
            entry.get("route_tag"),
            iso_mtime(path),
        ),
    )
    return image_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Import phase0 manifest into DB")
    parser.add_argument("--manifest", type=Path, default=PHASE0_MANIFEST)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        print("Run task 0.1 first (select_phase0_sample.py).", file=sys.stderr)
        return 1

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    conn = get_connection(args.db)

    imported = 0
    try:
        for entry in entries:
            import_entry(conn, entry)
            imported += 1
        conn.commit()
    finally:
        conn.close()

    print(f"Imported {imported} images from {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
