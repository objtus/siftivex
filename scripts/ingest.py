#!/usr/bin/env python3
"""Ingest one or more image files into DB (+ optional CLIP embed)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.config import archive_server_path, load_paths_config  # noqa: E402
from siftivex.db import get_connection  # noqa: E402
from siftivex.embeddings import Embedder, EmbeddingStore  # noqa: E402
from siftivex.folder_rules import load_folder_rules  # noqa: E402
from siftivex.ingest import collect_image_paths, ingest_file  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, DEFAULT_LANCE_PATH, FOLDER_RULES_PATH  # noqa: E402


def collect_paths(args: argparse.Namespace, paths_cfg: dict | None = None) -> list[Path]:
    if args.file:
        return [args.file.resolve()]
    root = None
    if args.dir:
        root = args.dir.resolve()
    elif args.archive:
        root = archive_server_path(args.archive, paths_cfg)
    if root is None:
        raise SystemExit("Specify --file, --dir, or --archive")

    return collect_image_paths(root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest images into siftivex DB")
    parser.add_argument("--file", type=Path, help="Single image file")
    parser.add_argument("--dir", type=Path, help="Directory (recursive)")
    parser.add_argument(
        "--archive",
        choices=["under_iphone", "pixiv_bookmarks"],
        help="Archive key from config/paths.yaml (uses server path)",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--folder-rules", type=Path, default=FOLDER_RULES_PATH)
    parser.add_argument("--paths-config", type=Path, default=None, help="Override paths.yaml")
    parser.add_argument("--lance", type=Path, default=DEFAULT_LANCE_PATH)
    parser.add_argument("--embed", action="store_true", help="Run CLIP embedding (requires [embed] extras)")
    parser.add_argument("--skip-thumbnails", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max files (0 = all)")
    parser.add_argument("--commit-every", type=int, default=100, help="SQLite commit interval")
    args = parser.parse_args()

    if args.paths_config:
        paths_cfg = load_paths_config(args.paths_config)
    else:
        paths_cfg = None

    paths = collect_paths(args, paths_cfg)
    if args.limit > 0:
        paths = paths[: args.limit]
    if not paths:
        print("No files to ingest.", file=sys.stderr)
        return 1

    embedder = store = None
    if args.embed:
        embedder = Embedder()
        store = EmbeddingStore(args.lance)

    folder_rules = load_folder_rules(args.folder_rules) if args.folder_rules.exists() else None

    conn = get_connection(args.db)
    stats = {"new": 0, "dup": 0, "embedded": 0, "thumb": 0, "ocr": 0, "ocr_q": 0, "err": 0}
    try:
        for i, path in enumerate(paths, start=1):
            try:
                result = ingest_file(
                    path,
                    conn,
                    folder_rules=folder_rules,
                    embedder=embedder,
                    store=store,
                    skip_thumbnails=args.skip_thumbnails,
                    skip_ocr=args.skip_ocr,
                )
            except Exception as exc:
                stats["err"] += 1
                print(f"err\t-\t{path.name}\t{exc}", file=sys.stderr)
                continue

            if result.is_new:
                stats["new"] += 1
            else:
                stats["dup"] += 1
            if result.embedded:
                stats["embedded"] += 1
            if result.thumbnails_created:
                stats["thumb"] += 1
            if result.ocr_done:
                stats["ocr"] += 1
            if result.ocr_queued:
                stats["ocr_q"] += 1

            status = "new" if result.is_new else "dup"
            print(f"{status}\t{result.image_id}\t{path.name}")

            if args.commit_every > 0 and i % args.commit_every == 0:
                conn.commit()
                print(f"... committed {i}/{len(paths)}", file=sys.stderr)
        conn.commit()
    finally:
        conn.close()

    print(
        "Done: "
        f"{len(paths)} files, {stats['new']} new, {stats['dup']} dup, "
        f"{stats['embedded']} embedded, {stats['thumb']} thumbs, "
        f"{stats['ocr']} ocr, {stats['ocr_q']} ocr queued, {stats['err']} errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
