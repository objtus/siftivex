#!/usr/bin/env python3
"""Compare role-based model stack backends on a fixed image set.

See docs/plans/model-stack-pilot.md and docs/decisions/role-based-model-stack.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.embeddings import Embedder  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, PHASE0_RESULTS, PILOT_MODEL_CACHE  # noqa: E402
from siftivex.pilot.config import load_pilot_config  # noqa: E402
from siftivex.pilot.d1_questions import build_d1_question_set  # noqa: E402
from siftivex.pilot.hardware import collect_hardware, track_peak_vram_mb  # noqa: E402

ALL_BACKENDS = ("clip_embed", "tagger_cl", "embedding_gemma2", "d1_3b", "legacy_vlm")


@dataclass
class BackendSummary:
    images: int = 0
    total_sec: float = 0.0
    errors: int = 0
    status: str = "ok"
    reason: str = ""
    peak_vram_mb: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageRow:
    source_path: str
    image_id: str | None = None
    clip_embed_sec: float | None = None
    clip_error: str | None = None
    clip_vector: list[float] | None = None
    tagger_tags: list[dict[str, Any]] | None = None
    tagger_error: str | None = None
    embed_gemma2: dict[str, Any] | None = None
    d1: dict[str, Any] | None = None
    d1_error: str | None = None
    legacy_vlm: dict[str, Any] | None = None


@dataclass
class PilotReport:
    created_at: str
    manifest: str | None
    backends_requested: list[str]
    hardware: dict[str, Any] = field(default_factory=dict)
    pilot_config: str | None = None
    backends: dict[str, dict[str, Any]] = field(default_factory=dict)
    per_image: list[dict[str, Any]] = field(default_factory=list)


def load_manifest(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries") or data.get("images") or []
    out: list[dict[str, str]] = []
    for e in entries:
        sp = e.get("source_path") or e.get("path")
        if sp:
            out.append({"source_path": sp, "route_tag": e.get("route_tag", "")})
    return out


def load_paths_file(path: Path) -> list[dict[str, str]]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [{"source_path": ln, "route_tag": ""} for ln in lines]


def load_from_db(db: Path, limit: int) -> list[dict[str, str]]:
    conn = get_connection(db)
    try:
        q = """
            SELECT image_id, source_path FROM images
            WHERE status = 'active' AND source_path IS NOT NULL
            ORDER BY image_id
        """
        if limit > 0:
            q += f" LIMIT {int(limit)}"
        rows = conn.execute(q).fetchall()
    finally:
        conn.close()
    return [{"source_path": r["source_path"], "image_id": r["image_id"], "route_tag": ""} for r in rows]


def enrich_image_ids(entries: list[dict[str, str]], db: Path) -> None:
    missing = [e for e in entries if not e.get("image_id")]
    if not missing:
        return
    conn = get_connection(db)
    try:
        for e in missing:
            row = conn.execute(
                "SELECT image_id FROM images WHERE source_path = ? AND status = 'active'",
                (e["source_path"],),
            ).fetchone()
            if row:
                e["image_id"] = row["image_id"]
    finally:
        conn.close()


def run_clip_embed(
    entries: list[dict[str, str]], rows: list[ImageRow], *, store_vectors: bool
) -> BackendSummary:
    summary = BackendSummary()
    embedder = Embedder()
    t0_all = time.perf_counter()
    with track_peak_vram_mb() as vram:
        for ent, row in zip(entries, rows, strict=False):
            path = Path(ent["source_path"])
            if not path.is_file():
                row.clip_error = "file not found"
                summary.errors += 1
                continue
            t0 = time.perf_counter()
            try:
                vec = embedder.embed_image(path)
                row.clip_embed_sec = round(time.perf_counter() - t0, 4)
                if store_vectors:
                    row.clip_vector = vec
                summary.images += 1
            except Exception as exc:  # noqa: BLE001
                row.clip_error = str(exc)
                summary.errors += 1
        summary.total_sec = round(time.perf_counter() - t0_all, 3)
        summary.peak_vram_mb = vram.get("peak_vram_mb")
    return summary


def run_tagger_cl(entries: list[dict[str, str]], rows: list[ImageRow], cfg: dict[str, Any], download: bool) -> BackendSummary:
    summary = BackendSummary()
    t_cfg = cfg.get("tagger") or {}
    cache = Path(t_cfg.get("cache_dir", PILOT_MODEL_CACHE / "cl_tagger"))
    try:
        from siftivex.pilot.tagger_cl import ClTaggerSession

        cuda_id = t_cfg.get("cuda_device_id")
        session = ClTaggerSession(
            cache_dir=cache,
            repo_id=t_cfg.get("repo_id", "cella110n/cl_tagger"),
            gen_threshold=float(t_cfg.get("general_threshold", 0.35)),
            char_threshold=float(t_cfg.get("character_threshold", 0.85)),
            max_tags=int(t_cfg.get("max_tags", 64)),
            download=download,
            cuda_device_id=int(cuda_id) if cuda_id is not None else None,
        )
        summary.extra["provider"] = session.provider
        if cuda_id is not None:
            summary.extra["cuda_device_id"] = int(cuda_id)
    except Exception as exc:  # noqa: BLE001
        summary.status = "error"
        summary.reason = str(exc)
        return summary

    t0_all = time.perf_counter()
    with track_peak_vram_mb() as vram:
        for ent, row in zip(entries, rows, strict=False):
            path = Path(ent["source_path"])
            if not path.is_file():
                row.tagger_error = "file not found"
                summary.errors += 1
                continue
            try:
                row.tagger_tags = session.tag_path(path)
                summary.images += 1
            except Exception as exc:  # noqa: BLE001
                row.tagger_error = str(exc)
                summary.errors += 1
        summary.total_sec = round(time.perf_counter() - t0_all, 3)
        summary.peak_vram_mb = vram.get("peak_vram_mb")
    return summary


def run_embedding_gemma2(
    entries: list[dict[str, str]], rows: list[ImageRow], cfg: dict[str, Any], *, store_vectors: bool
) -> BackendSummary:
    summary = BackendSummary()
    eg = cfg.get("embedding_gemma2") or {}
    try:
        from siftivex.pilot.embed_gemma2 import Gemma2Embedder

        embedder = Gemma2Embedder(
            model_id=eg.get("model_id", "google/embeddinggemma-2"),
            dtype=eg.get("dtype", "bfloat16"),
            device=eg.get("device"),
        )
        summary.extra["dtype"] = embedder.dtype
        summary.extra["device"] = embedder.device
    except Exception as exc:  # noqa: BLE001
        summary.status = "error"
        summary.reason = str(exc)
        return summary

    t0_all = time.perf_counter()
    with track_peak_vram_mb() as vram:
        for ent, row in zip(entries, rows, strict=False):
            path = Path(ent["source_path"])
            if not path.is_file():
                row.embed_gemma2 = {"error": "file not found"}
                summary.errors += 1
                continue
            t0 = time.perf_counter()
            try:
                vec = embedder.embed_image_path(path)
                block: dict[str, Any] = {"sec": round(time.perf_counter() - t0, 4), "dim": len(vec)}
                if store_vectors:
                    block["vector"] = vec
                row.embed_gemma2 = block
                summary.images += 1
            except Exception as exc:  # noqa: BLE001
                row.embed_gemma2 = {"error": str(exc)}
                summary.errors += 1
        summary.total_sec = round(time.perf_counter() - t0_all, 3)
        summary.peak_vram_mb = vram.get("peak_vram_mb")
    return summary


def _tagger_hint(row: ImageRow) -> str | None:
    if not row.tagger_tags:
        return None
    tags = [t["tag"] for t in row.tagger_tags[:10]]
    return "tagger hints: " + ", ".join(tags)


def run_d1_3b(entries: list[dict[str, str]], rows: list[ImageRow], cfg: dict[str, Any], download: bool) -> BackendSummary:
    _ = download
    summary = BackendSummary()
    d1_cfg = cfg.get("d1") or {}
    questions = build_d1_question_set(cfg, include_namespace=True)
    summary.extra["question_count"] = len(questions)
    try:
        from siftivex.pilot.d1_runner import D1Runner

        prefer_cuda = bool(d1_cfg.get("prefer_cuda", False))
        runner = D1Runner(
            model_id=d1_cfg.get("model_id", "LiquidAI/d1-3B"),
            prefer_cuda=prefer_cuda,
            device=d1_cfg.get("device"),
        )
    except Exception as exc:  # noqa: BLE001
        summary.status = "error"
        summary.reason = str(exc)
        return summary

    t0_all = time.perf_counter()
    with track_peak_vram_mb() as vram:
        for ent, row in zip(entries, rows, strict=False):
            path = Path(ent["source_path"])
            if not path.is_file():
                row.d1_error = "file not found"
                summary.errors += 1
                continue
            t0 = time.perf_counter()
            try:
                state = _tagger_hint(row)
                out = runner.decide(path, questions, state_text=state)
                row.d1 = {"sec": round(time.perf_counter() - t0, 4), **out}
                summary.images += 1
            except Exception as exc:  # noqa: BLE001
                row.d1_error = str(exc)
                summary.errors += 1
        summary.total_sec = round(time.perf_counter() - t0_all, 3)
        summary.peak_vram_mb = vram.get("peak_vram_mb")
    return summary


def run_legacy_vlm(entries: list[dict[str, str]], rows: list[ImageRow]) -> BackendSummary:
    from siftivex.vlm import VlmClient

    summary = BackendSummary()
    client = VlmClient()
    t0_all = time.perf_counter()
    for ent, row in zip(entries, rows, strict=False):
        path = Path(ent["source_path"])
        if not path.is_file():
            summary.errors += 1
            continue
        t0 = time.perf_counter()
        try:
            result = client.tag_image(path)
            row.legacy_vlm = {
                "sec": round(time.perf_counter() - t0, 3),
                "flat_tags": result.flat_tags[:20],
                "namespace": result.namespace_tags,
                "caption_len": len(result.caption or ""),
            }
            summary.images += 1
        except Exception as exc:  # noqa: BLE001
            row.legacy_vlm = {"error": str(exc)}
            summary.errors += 1
    summary.total_sec = round(time.perf_counter() - t0_all, 3)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Model stack pilot (see docs/plans/model-stack-pilot.md)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--manifest", type=Path, help="Phase 0 manifest JSON")
    src.add_argument("--paths-file", type=Path, help="Newline-separated image paths")
    src.add_argument("--from-db", action="store_true", help="Use active images from SQLite")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--limit", type=int, default=0, help="Max images (from-db or manifest)")
    parser.add_argument(
        "--backends",
        type=str,
        default="clip_embed",
        help=f"Comma-separated: {','.join(ALL_BACKENDS)}",
    )
    parser.add_argument("--config", type=Path, help="model_stack_pilot.yaml")
    parser.add_argument("--download-models", action="store_true", help="Allow HF download for tagger/d1/gemma")
    parser.add_argument(
        "--store-vectors",
        action="store_true",
        help="Store clip/gemma vectors in JSON (large files)",
    )
    parser.add_argument(
        "--include-legacy-vlm",
        action="store_true",
        help="Allow legacy_vlm in --backends (slow; hits llama-server)",
    )
    parser.add_argument("--output", type=Path, help="JSON report path")
    args = parser.parse_args()

    cfg = load_pilot_config(args.config)

    if args.manifest:
        entries = load_manifest(args.manifest)
        manifest_ref = str(args.manifest)
    elif args.paths_file:
        entries = load_paths_file(args.paths_file)
        manifest_ref = str(args.paths_file)
    else:
        entries = load_from_db(args.db, args.limit)
        manifest_ref = str(args.db)

    if args.limit > 0 and args.manifest:
        entries = entries[: args.limit]

    enrich_image_ids(entries, args.db)

    if not entries:
        print("No images to process.", file=sys.stderr)
        return 1

    requested = [b.strip() for b in args.backends.split(",") if b.strip()]
    unknown = set(requested) - set(ALL_BACKENDS)
    if unknown:
        print(f"Unknown backends: {unknown}", file=sys.stderr)
        return 1
    if "legacy_vlm" in requested and not args.include_legacy_vlm:
        print("Refusing legacy_vlm without --include-legacy-vlm", file=sys.stderr)
        return 1

    report = PilotReport(
        created_at=datetime.now(timezone.utc).isoformat(),
        manifest=manifest_ref,
        backends_requested=requested,
        hardware=collect_hardware(),
        pilot_config=str(args.config) if args.config else None,
    )

    rows: list[ImageRow] = [
        ImageRow(source_path=e["source_path"], image_id=e.get("image_id")) for e in entries
    ]

    for backend in requested:
        if backend == "clip_embed":
            summary = run_clip_embed(entries, rows, store_vectors=args.store_vectors)
        elif backend == "tagger_cl":
            summary = run_tagger_cl(entries, rows, cfg, args.download_models)
        elif backend == "embedding_gemma2":
            summary = run_embedding_gemma2(entries, rows, cfg, store_vectors=args.store_vectors)
        elif backend == "d1_3b":
            summary = run_d1_3b(entries, rows, cfg, args.download_models)
        elif backend == "legacy_vlm":
            summary = run_legacy_vlm(entries, rows)
        else:
            continue
        report.backends[backend] = asdict(summary)
        print(
            f"{backend}: {summary.status} images={summary.images} sec={summary.total_sec} "
            f"err={summary.errors} vram={summary.peak_vram_mb}"
        )

    report.per_image = [asdict(r) for r in rows]

    out = args.output
    if out is None:
        PHASE0_RESULTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = PHASE0_RESULTS / f"model_stack_pilot_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
