#!/usr/bin/env python3
"""Task 0.1: Generate phase0 manifest via stratified sampling."""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.config import load_phase0_config  # noqa: E402
from siftivex.paths import PHASE0_MANIFEST  # noqa: E402


def collect_images(source_path: Path, extensions: set[str]) -> list[Path]:
    if not source_path.exists():
        raise FileNotFoundError(f"Source path not found: {source_path}")

    files: list[Path] = []
    for path in source_path.rglob("*"):
        if path.is_file() and path.suffix.lower() in extensions:
            files.append(path.resolve())
    return files


def sample_paths(files: list[Path], count: int, seed: int) -> list[Path]:
    if len(files) <= count:
        return files
    rng = random.Random(seed)
    return rng.sample(files, count)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select Phase 0 sample images")
    parser.add_argument("--config", type=Path, help="Path to phase0.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Print stats only")
    args = parser.parse_args()

    cfg = load_phase0_config(args.config)
    extensions = {ext.lower() for ext in cfg.get("extensions", [])}
    seed = int(cfg.get("seed", 42))
    output = Path(cfg.get("output", {}).get("manifest", PHASE0_MANIFEST))

    entries: list[dict[str, str]] = []
    for source in cfg.get("sources", []):
        route_tag = source["route_tag"]
        path = Path(source["path"]).expanduser()
        count = int(source.get("count", 0))
        files = collect_images(path, extensions)
        picked = sample_paths(files, count, seed)
        print(f"{route_tag}: {len(picked)}/{len(files)} from {path}")
        for p in sorted(picked):
            entries.append({"source_path": str(p), "route_tag": route_tag, "note": ""})

    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "entries": entries,
    }

    if args.dry_run:
        print(f"Total entries: {len(entries)} (dry run, not written)")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
