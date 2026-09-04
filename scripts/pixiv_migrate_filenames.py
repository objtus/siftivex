#!/usr/bin/env python3
"""Rename long pixiv filenames and write .pixiv.json sidecars (run on Windows sender)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.pixiv_filename import (  # noqa: E402
    filename_byte_length,
    parse_pixiv_filename,
    parse_pixiv_filename_fallback,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".webm"}


def iter_images(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.iterdir():
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            files.append(path)
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Shorten pixiv filenames and preserve metadata in sidecar JSON"
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Pixiv folder (e.g. D:/公開ブクマ on Windows)",
    )
    parser.add_argument(
        "--min-bytes",
        type=int,
        default=240,
        help="Rename when filename byte length exceeds this (default: 240, Linux limit 255)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Rename all parseable pixiv files, not only long names",
    )
    parser.add_argument(
        "--drop-long-duplicates",
        action="store_true",
        help="When short name already exists, delete the long duplicate",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply renames (default: dry-run)",
    )
    args = parser.parse_args()

    if not args.source.is_dir():
        print(f"Not a directory: {args.source}", file=sys.stderr)
        return 1

    planned = 0
    skipped = 0
    unparsed = 0
    fallback = 0
    dup_deleted = 0
    conflicts = 0

    for path in iter_images(args.source):
        meta = parse_pixiv_filename(path.name)
        if meta is None and filename_byte_length(path.name) > args.min_bytes:
            meta = parse_pixiv_filename_fallback(path.name)
        if meta is None:
            if filename_byte_length(path.name) > args.min_bytes:
                print(f"  SKIP (unparsed, long): {path.name[:80]}...")
            unparsed += 1
            continue
        if meta.parse_mode == "fallback":
            fallback += 1

        short = meta.short_filename()
        sidecar = path.with_name(meta.sidecar_filename())
        too_long = filename_byte_length(path.name) > args.min_bytes
        already_short = path.name == short and sidecar.exists()

        if already_short:
            skipped += 1
            continue
        if not args.all and not too_long:
            skipped += 1
            continue

        target = path.with_name(short)
        if target.exists() and target != path:
            if args.drop_long_duplicates:
                dup_deleted += 1
                action = "DELETE-DUP" if args.apply else "DRY-DUP"
                print(f"  {action} {path.name[:70]}...")
                print(f"         (keep {short})")
                if args.apply:
                    if not sidecar.exists():
                        sidecar.write_text(meta.to_json(), encoding="utf-8")
                    path.unlink()
                continue
            conflicts += 1
            print(f"  CONFLICT: {short} already exists (from {path.name[:60]}...)")
            continue

        planned += 1
        action = "RENAME" if args.apply else "DRY-RUN"
        mode_note = f" [{meta.parse_mode}]" if meta.parse_mode != "full" else ""
        print(f"  {action}{mode_note} {path.name[:70]}...")
        print(f"         -> {short} + {sidecar.name}")

        if args.apply:
            sidecar.write_text(meta.to_json(), encoding="utf-8")
            path.rename(target)

    print()
    print(
        f"Planned: {planned}, dup-delete: {dup_deleted}, conflicts: {conflicts}, "
        f"skipped: {skipped}, unparsed: {unparsed}, fallback: {fallback}"
    )
    if not args.apply and (planned or dup_deleted):
        print("Re-run with --apply to execute. Pause Syncthing before applying.")
    if conflicts and not args.drop_long_duplicates:
        print("CONFLICT present — re-run with --drop-long-duplicates to remove long copies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
