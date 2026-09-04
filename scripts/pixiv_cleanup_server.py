#!/usr/bin/env python3
"""Remove orphaned long pixiv filenames on Linux after Windows rename.

When Windows renames date_*...jpg -> 4826_p0.jpg, Syncthing must delete the old
name on the receiver. Linux cannot lstat paths >255 bytes, so deletion stalls
and .syncthing.*.tmp files accumulate. This script deletes long names when a
matching short file (+ optional sidecar) already exists.

Run with Syncthing paused on the pixiv folder.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.pixiv_filename import parse_pixiv_filename  # noqa: E402

SHORT_RE = re.compile(r"^(?P<work_id>\d+)(?:_p(?P<page>\d+))?\.(?P<ext>[^.]+)$", re.I)
WORK_ID_RE = re.compile(r"(?:id_|_)(?P<work_id>\d+)(?:_p(?P<page>\d+))?", re.I)


def short_key(work_id: str, page: int | None, ext: str) -> str:
    if page is not None:
        return f"{work_id}_p{page}.{ext.lower()}"
    return f"{work_id}.{ext.lower()}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete orphaned long pixiv files on Linux")
    parser.add_argument("folder", type=Path, help="Pixiv sync folder on server")
    parser.add_argument("--apply", action="store_true", help="Delete files (default: dry-run)")
    parser.add_argument(
        "--clean-tmp",
        action="store_true",
        help="Also remove stale .syncthing.*.tmp files",
    )
    args = parser.parse_args()

    folder = args.folder
    if not folder.is_dir():
        print(f"Not a directory: {folder}", file=sys.stderr)
        return 1

    short_names: set[str] = set()
    for path in folder.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        m = SHORT_RE.match(path.name)
        if m:
            short_names.add(path.name.lower())

    planned = 0
    tmp_planned = 0

    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name.startswith(".syncthing") and name.endswith(".tmp"):
            if args.clean_tmp:
                tmp_planned += 1
                if args.apply:
                    path.unlink()
            continue
        if not name.startswith("date_"):
            continue

        meta = parse_pixiv_filename(name)
        if meta is not None:
            candidate = meta.short_filename().lower()
        else:
            m = WORK_ID_RE.search(name)
            if not m:
                continue
            ext = path.suffix.lstrip(".").lower()
            page = m.group("page")
            candidate = short_key(
                m.group("work_id"),
                int(page) if page is not None else None,
                ext,
            )

        if candidate in short_names:
            planned += 1
            action = "DELETE" if args.apply else "DRY-RUN"
            print(f"  {action} {name[:90]}...")
            if args.apply:
                path.unlink()

    print()
    print(f"Orphan long files: {planned}")
    if args.clean_tmp:
        print(f"Stale tmp files: {tmp_planned}")
    if not args.apply and (planned or tmp_planned):
        print("Re-run with --apply (pause Syncthing first).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
