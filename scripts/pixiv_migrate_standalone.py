#!/usr/bin/env python3
"""Rename long pixiv filenames and write .pixiv.json sidecars.

Self-contained — stdlib only. Windows ではこのファイル1つだけ取得すればよい
（リポジトリ clone 不要）。ロジックは src/siftivex/pixiv_filename.py と同期すること。

Usage:
  py -3 pixiv_migrate_standalone.py "<pixiv-folder>"
  py -3 pixiv_migrate_standalone.py "<pixiv-folder>" --apply
  py -3 pixiv_migrate_standalone.py "<pixiv-folder>" --apply --drop-long-duplicates
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_WORK_ID = r"(?:id_|_)(?P<work_id>\d+)"

PIXIV_WITH_TAGS_RE = re.compile(
    r"^date_(?P<posted_at>\d{4}-\d{2}-\d{2})"
    + _WORK_ID
    + r"(?:_p(?P<page>\d+))?"
    r"user_(?P<artist>.+?)"
    r"title_(?P<title>.+?)"
    r"_tags_(?P<pixiv_tags>.+?)"
    r"\.(?P<ext>[^.]+)$",
    re.UNICODE,
)

PIXIV_NO_TAGS_KEYWORD_RE = re.compile(
    r"^date_(?P<posted_at>\d{4}-\d{2}-\d{2})"
    + _WORK_ID
    + r"(?:_p(?P<page>\d+))?"
    r"user_(?P<artist>.+?)"
    r"title_(?P<title>.+?)_(?P<pixiv_tags>.+?)"
    r"\.(?P<ext>[^.]+)$",
    re.UNICODE,
)

PIXIV_FALLBACK_RE = re.compile(
    r"^date_(?P<posted_at>\d{4}-\d{2}-\d{2})"
    + _WORK_ID
    + r"(?:_p(?P<page>\d+))?"
    r".*\.(?P<ext>[^.]+)$",
    re.UNICODE,
)

SIDECAR_SUFFIX = ".pixiv.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".webm"}


@dataclass(frozen=True)
class PixivFilenameMeta:
    original_filename: str
    posted_at: str
    work_id: str
    page: int | None
    artist: str
    title: str
    pixiv_tags: list[str]
    ext: str
    parse_mode: str = "full"

    @property
    def source_url(self) -> str:
        return f"https://www.pixiv.net/artworks/{self.work_id}"

    def short_filename(self) -> str:
        if self.page is not None:
            return f"{self.work_id}_p{self.page}.{self.ext}"
        return f"{self.work_id}.{self.ext}"

    def sidecar_filename(self) -> str:
        return f"{Path(self.short_filename()).stem}{SIDECAR_SUFFIX}"

    def to_sidecar_dict(self) -> dict:
        data = {
            "version": 1,
            "original_filename": self.original_filename,
            "posted_at": self.posted_at,
            "work_id": self.work_id,
            "page": self.page,
            "artist": self.artist,
            "title": self.title,
            "pixiv_tags": self.pixiv_tags,
            "source_url": self.source_url,
        }
        if self.parse_mode != "full":
            data["parse_mode"] = self.parse_mode
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_sidecar_dict(), ensure_ascii=False, indent=2) + "\n"


def _meta_from_match(
    filename: str,
    groups: dict[str, str | None],
    *,
    parse_mode: str,
) -> PixivFilenameMeta:
    tags_raw = groups.get("pixiv_tags") or ""
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    page = groups.get("page")
    return PixivFilenameMeta(
        original_filename=filename,
        posted_at=groups["posted_at"] or "",
        work_id=groups["work_id"] or "",
        page=int(page) if page is not None else None,
        artist=groups.get("artist") or "",
        title=groups.get("title") or "",
        pixiv_tags=tags,
        ext=groups["ext"] or "",
        parse_mode=parse_mode,
    )


def parse_pixiv_filename(filename: str) -> PixivFilenameMeta | None:
    for pattern, mode in (
        (PIXIV_WITH_TAGS_RE, "full"),
        (PIXIV_NO_TAGS_KEYWORD_RE, "no_tags_keyword"),
    ):
        match = pattern.match(filename)
        if match:
            return _meta_from_match(filename, match.groupdict(), parse_mode=mode)
    return None


def parse_pixiv_filename_fallback(filename: str) -> PixivFilenameMeta | None:
    match = PIXIV_FALLBACK_RE.match(filename)
    if not match:
        return None
    return _meta_from_match(
        filename,
        {**match.groupdict(), "artist": "", "title": "", "pixiv_tags": ""},
        parse_mode="fallback",
    )


def resolve_meta(filename: str, min_bytes: int) -> PixivFilenameMeta | None:
    meta = parse_pixiv_filename(filename)
    if meta is not None:
        return meta
    if filename_byte_length(filename) > min_bytes:
        return parse_pixiv_filename_fallback(filename)
    return None


def filename_byte_length(name: str) -> int:
    return len(name.encode("utf-8"))


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
    parser.add_argument("source", type=Path, help="Pixiv image folder on Windows")
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
        meta = resolve_meta(path.name, args.min_bytes)
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
