"""Ingest a single image: DB registration, metadata, embedding."""

from __future__ import annotations

import json
import mimetypes
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from siftivex.embeddings import EmbedResult, Embedder, EmbeddingStore
from siftivex.filename_tags import parse_legacy_filename_tags
from siftivex.folder_rules import FolderRules, IngestProfile, load_folder_rules
from siftivex.ids import content_hash, image_id_from_hash
from siftivex.ocr import ocr_engine_available, run_ocr
from siftivex.pixiv_filename import parse_pixiv_filename
from siftivex.search_index import upsert_image_search
from siftivex.tags_db import apply_filename_tags, replace_tags
from siftivex.thumbnails import generate_thumbnails, supports_thumbnails

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".webm"}


def collect_image_paths(root: Path) -> list[Path]:
    """Collect image files under root (case-insensitive extension match)."""
    found: set[Path] = set()
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            found.add(path.resolve())
    return sorted(found)


@dataclass(frozen=True)
class IngestResult:
    image_id: str
    path: Path
    is_new: bool
    embedded: bool
    route_tag: str | None
    metadata_written: bool
    vlm_queued: bool
    thumbnails_created: bool
    ocr_done: bool
    ocr_queued: bool
    search_indexed: bool


def iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat()


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return None, None


def resolve_pixiv_metadata(path: Path) -> dict | None:
    sidecar = path.with_name(f"{path.stem}.pixiv.json")
    if sidecar.is_file():
        return json.loads(sidecar.read_text(encoding="utf-8"))
    meta = parse_pixiv_filename(path.name)
    if meta is not None:
        return meta.to_sidecar_dict()
    return None


def upsert_image_row(
    conn: sqlite3.Connection,
    path: Path,
    *,
    route_tag: str | None,
) -> tuple[str, bool]:
    full_hash = content_hash(path)
    image_id = image_id_from_hash(full_hash)
    existing = conn.execute(
        "SELECT image_id FROM images WHERE content_hash = ?",
        (full_hash,),
    ).fetchone()
    is_new = existing is None

    width, height = image_dimensions(path)
    mime_type, _ = mimetypes.guess_type(path.name)

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
            str(path.resolve()),
            path.name,
            path.stat().st_size,
            width,
            height,
            mime_type,
            route_tag,
            iso_mtime(path),
        ),
    )
    return image_id, is_new


def write_pixiv_metadata(conn: sqlite3.Connection, image_id: str, meta: dict) -> None:
    extra = {
        k: meta[k]
        for k in ("title", "page", "pixiv_tags", "original_filename", "parse_mode")
        if k in meta and meta[k] is not None
    }
    conn.execute(
        """
        INSERT INTO image_metadata (image_id, artist, work_id, posted_at, source_url, extra_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(image_id) DO UPDATE SET
            artist      = excluded.artist,
            work_id     = excluded.work_id,
            posted_at   = excluded.posted_at,
            source_url  = excluded.source_url,
            extra_json  = excluded.extra_json
        """,
        (
            image_id,
            meta.get("artist") or None,
            meta.get("work_id") or None,
            meta.get("posted_at") or None,
            meta.get("source_url") or None,
            json.dumps(extra, ensure_ascii=False) if extra else None,
        ),
    )


def apply_profile_tags(conn: sqlite3.Connection, image_id: str, path: Path, profile: IngestProfile) -> None:
    if profile.fixed_tags:
        replace_tags(conn, image_id, "manual_added", list(profile.fixed_tags))
    if profile.parser == "under_iphone_legacy_v1":
        apply_filename_tags(conn, image_id, path.name)
    elif profile.metadata == "pixiv_hybrid":
        if parse_legacy_filename_tags(path.name):
            apply_filename_tags(conn, image_id, path.name)


def write_auto_ocr(conn: sqlite3.Connection, image_id: str, text: str) -> None:
    conn.execute(
        """
        INSERT INTO image_ocr (image_id, auto_ocr)
        VALUES (?, ?)
        ON CONFLICT(image_id) DO UPDATE SET
            auto_ocr = excluded.auto_ocr,
            updated_at = datetime('now')
        """,
        (image_id, text),
    )


def queue_index_job(conn: sqlite3.Connection, image_id: str, job_type: str) -> bool:
    pending = conn.execute(
        """
        SELECT 1 FROM index_jobs
        WHERE image_id = ? AND job_type = ? AND status IN ('pending', 'running')
        """,
        (image_id, job_type),
    ).fetchone()
    if pending:
        return False
    conn.execute(
        """
        INSERT INTO index_jobs (image_id, job_type, status)
        VALUES (?, ?, 'pending')
        """,
        (image_id, job_type),
    )
    return True


def queue_vlm_job(conn: sqlite3.Connection, image_id: str) -> bool:
    return queue_index_job(conn, image_id, "vlm_tag")


def queue_ocr_job(conn: sqlite3.Connection, image_id: str) -> bool:
    return queue_index_job(conn, image_id, "ocr")


def run_profile_ocr(
    conn: sqlite3.Connection,
    image_id: str,
    path: Path,
    profile: IngestProfile | None,
) -> tuple[bool, bool]:
    """Returns (ocr_done, ocr_queued)."""
    engine = profile.ocr_engine if profile else None
    if not engine or engine == "skip":
        return False, False

    if not ocr_engine_available(engine):
        return False, queue_ocr_job(conn, image_id)

    try:
        text = run_ocr(path, engine)
    except Exception:
        return False, queue_ocr_job(conn, image_id)

    write_auto_ocr(conn, image_id, text)
    return True, False


def ingest_file(
    path: Path,
    conn: sqlite3.Connection,
    *,
    folder_rules: FolderRules | None = None,
    embedder: Embedder | None = None,
    store: EmbeddingStore | None = None,
    route_tag: str | None = None,
    force_embed: bool = False,
    skip_thumbnails: bool = False,
    skip_ocr: bool = False,
    skip_search_index: bool = False,
) -> IngestResult:
    """Register one image and run ingest-side indexing (new content only)."""
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported extension: {path.suffix}")

    rules = folder_rules
    profile = rules.match(path) if rules else None
    resolved_route = route_tag or (profile.route_tag if profile else None)

    image_id, is_new = upsert_image_row(conn, path, route_tag=resolved_route)

    metadata_written = False
    if profile and profile.metadata == "pixiv_hybrid":
        meta = resolve_pixiv_metadata(path)
        if meta:
            write_pixiv_metadata(conn, image_id, meta)
            metadata_written = True
    if profile:
        apply_profile_tags(conn, image_id, path, profile)

    thumbnails_created = False
    ocr_done = False
    ocr_queued = False
    embedded = False
    search_indexed = False

    if is_new:
        if not skip_thumbnails and supports_thumbnails(path):
            try:
                generate_thumbnails(path, image_id)
                thumbnails_created = True
            except Exception:
                pass

        if not skip_ocr:
            ocr_done, ocr_queued = run_profile_ocr(conn, image_id, path, profile)

        if embedder is not None and store is not None:
            try:
                vector = embedder.embed_image(path)
                store.upsert([EmbedResult(image_id=image_id, vector=vector, model=embedder.model_label)])
                conn.execute(
                    """
                    UPDATE images
                    SET indexed_at = datetime('now'), updated_at = datetime('now')
                    WHERE image_id = ?
                    """,
                    (image_id,),
                )
                embedded = True
            except Exception:
                pass

        if not skip_search_index:
            upsert_image_search(conn, image_id)
            search_indexed = True

    vlm_queued = False
    if is_new:
        vlm_queued = queue_vlm_job(conn, image_id)

    return IngestResult(
        image_id=image_id,
        path=path,
        is_new=is_new,
        embedded=embedded,
        route_tag=resolved_route,
        metadata_written=metadata_written,
        vlm_queued=vlm_queued,
        thumbnails_created=thumbnails_created,
        ocr_done=ocr_done,
        ocr_queued=ocr_queued,
        search_indexed=search_indexed,
    )


def ingest_paths(
    paths: list[Path],
    conn: sqlite3.Connection,
    *,
    folder_rules_path: Path | None = None,
    embedder: Embedder | None = None,
    store: EmbeddingStore | None = None,
    commit_every: int = 100,
    **kwargs,
) -> list[IngestResult]:
    rules = load_folder_rules(folder_rules_path) if folder_rules_path else None
    results: list[IngestResult] = []
    for i, path in enumerate(paths, start=1):
        results.append(
            ingest_file(
                path,
                conn,
                folder_rules=rules,
                embedder=embedder,
                store=store,
                **kwargs,
            )
        )
        if commit_every > 0 and i % commit_every == 0:
            conn.commit()
    conn.commit()
    return results
