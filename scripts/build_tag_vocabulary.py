#!/usr/bin/env python3
"""Build preferred tag vocabulary from filename tags in an archive folder."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.filename_tags import parse_legacy_filename_tags  # noqa: E402
from siftivex.paths import TAG_VOCABULARY_PATH  # noqa: E402
from siftivex.tag_vocabulary import (  # noqa: E402
    DEFAULT_EXCLUDE_FLAT_TAGS,
    DEFAULT_NOISE_PATTERNS,
    is_noise_tag,
    load_tag_vocabulary,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}


def collect_tags(source: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in source.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            for tag in parse_legacy_filename_tags(path.name):
                counts[tag] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build tag_vocabulary.yaml from filenames")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("/home/objtus/Sync/siftivex-archive/under.iphone"),
        help="Archive folder to scan",
    )
    parser.add_argument("--min-count", type=int, default=2, help="Minimum occurrence to include")
    parser.add_argument("--output", type=Path, default=TAG_VOCABULARY_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Source not found: {args.source}", file=sys.stderr)
        return 1

    counts = collect_tags(args.source)
    existing = load_tag_vocabulary(args.output) if args.output.exists() else {}
    aliases = dict(existing.get("aliases", {}))
    noise_patterns = existing.get("noise_patterns") or DEFAULT_NOISE_PATTERNS
    exclude_flat_tags = set(existing.get("exclude_flat_tags") or DEFAULT_EXCLUDE_FLAT_TAGS)
    manual_flat_tags = existing.get("manual_flat_tags", [])
    tag_notes = existing.get("tag_notes", {})

    canonical_counts: Counter[str] = Counter()
    skipped_noise = 0
    skipped_exclude = 0
    for tag, count in counts.items():
        if is_noise_tag(tag, noise_patterns):
            skipped_noise += 1
            continue
        canonical = aliases.get(tag, tag)
        if canonical in exclude_flat_tags:
            skipped_exclude += 1
            continue
        canonical_counts[canonical] += count

    deduped = [
        {"tag": tag, "count": count}
        for tag, count in canonical_counts.most_common()
        if count >= args.min_count
    ]

    doc = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": str(args.source.resolve()),
        "min_count": args.min_count,
        "preferred_flat_tags": deduped,
        "manual_flat_tags": manual_flat_tags,
        "tag_notes": tag_notes,
        "aliases": aliases,
        "exclude_flat_tags": sorted(exclude_flat_tags),
        "noise_patterns": noise_patterns,
    }

    if args.dry_run:
        print(yaml.dump(doc, allow_unicode=True, sort_keys=False))
        print(
            f"# auto: {len(deduped)}, manual: {len(manual_flat_tags)}, "
            f"skipped_noise: {skipped_noise}, skipped_exclude: {skipped_exclude}"
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    total = len(deduped) + len(manual_flat_tags)
    print(f"Wrote {len(deduped)} auto + {len(manual_flat_tags)} manual tags ({total} total) to {args.output}")
    print(f"Skipped {skipped_noise} noise, {skipped_exclude} excluded (min_count={args.min_count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
