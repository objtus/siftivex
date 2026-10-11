"""FastAPI application skeleton."""

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from siftivex.db import get_connection
from siftivex.embeddings import Embedder, EmbeddingStore
from siftivex.jobs import retag_image
from siftivex.paths import DEFAULT_DB_PATH, DEFAULT_LANCE_PATH, DEFAULT_THUMBNAILS_DIR
from siftivex.search import image_to_dict, search_images
from siftivex.tag_vocabulary import PROMPT_REVISION
from siftivex.tag_stack_status import tag_stack_by_route, tag_stack_summary
from siftivex.tags_db import effective_tags, tags_grouped_by_source
from siftivex.thumbnails import ThumbnailPaths, thumbnail_dir
from siftivex.vlm import VlmClient
from siftivex.works import get_work_pages, image_metadata_for_image, validate_work_id, work_context_for_image

app = FastAPI(title="Siftivex", version="0.2.0")


@lru_cache(maxsize=1)
def _embedder() -> Embedder:
    return Embedder()


@lru_cache(maxsize=1)
def _embedding_store() -> EmbeddingStore:
    return EmbeddingStore(DEFAULT_LANCE_PATH)


def _vlm_client() -> VlmClient:
    """New client each call so config/vlm.yaml changes apply without API restart."""
    return VlmClient()


def _thumb_paths(image_id: str) -> ThumbnailPaths:
    base = thumbnail_dir(image_id, DEFAULT_THUMBNAILS_DIR)
    return ThumbnailPaths(thumb=base / "thumb.webp", preview=base / "preview.webp")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "prompt_revision": PROMPT_REVISION}


@app.get("/api/images")
def list_images(
    q: str = Query("", description="tag:foo -tag:bar or natural language"),
    include_tag: list[str] = Query(
        default=[],
        description="Repeat for each include tag (spaces OK, e.g. bare legs)",
    ),
    exclude_tag: list[str] = Query(default=[], description="Repeat for each exclude tag"),
    route_tag: str | None = Query(None),
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    conn = get_connection(DEFAULT_DB_PATH)
    try:
        parsed = search_images(
            conn,
            q,
            route_tag=route_tag,
            limit=limit,
            offset=offset,
            store=_embedding_store(),
            embedder=_embedder(),
            extra_include_tags=include_tag,
            extra_exclude_tags=exclude_tag,
        )
        return {
            "total": parsed.total,
            "limit": limit,
            "offset": offset,
            "query": {
                "raw": q,
                "include_tags": parsed.parsed.include_tags,
                "exclude_tags": parsed.parsed.exclude_tags,
                "text": parsed.parsed.text,
            },
            "items": [image_to_dict(conn, hit) for hit in parsed.items],
        }
    finally:
        conn.close()


def _has_thumbnail(image_id: str) -> bool:
    return _thumb_paths(image_id).thumb.is_file()


@app.get("/api/images/{image_id}")
def get_image(image_id: str) -> dict:
    conn = get_connection(DEFAULT_DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT image_id, file_name, route_tag, width, height, vlm_caption, source_path, status
            FROM images WHERE image_id = ?
            """,
            (image_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="image not found")
        tags = effective_tags(conn, image_id)
        tag_sources = tags_grouped_by_source(conn, image_id)
        ocr = conn.execute(
            "SELECT COALESCE(manual_ocr, auto_ocr, '') AS text FROM image_ocr WHERE image_id = ?",
            (image_id,),
        ).fetchone()
        work = work_context_for_image(conn, image_id)
        metadata = image_metadata_for_image(conn, image_id)
    finally:
        conn.close()

    thumbs = _thumb_paths(image_id)
    return {
        "image_id": row["image_id"],
        "file_name": row["file_name"],
        "route_tag": row["route_tag"],
        "width": row["width"],
        "height": row["height"],
        "vlm_caption": row["vlm_caption"],
        "status": row["status"],
        "tags": tags,
        "tag_sources": {
            "auto": tag_sources["auto"],
            "filename": tag_sources["filename"],
            "auto_tagger": tag_sources["auto_tagger"],
            "auto_d1": tag_sources["auto_d1"],
            "inferred_ja": tag_sources["inferred_ja"],
            "manual_added": tag_sources["manual_added"],
        },
        "prompt_revision": PROMPT_REVISION,
        "ocr_text": ocr["text"] if ocr else "",
        "has_thumbnail": thumbs.thumb.is_file(),
        "has_preview": thumbs.preview.is_file(),
        "metadata": metadata,
        "work": work,
    }


@app.post("/api/images/{image_id}/retag")
def retag_image_endpoint(image_id: str) -> dict:
    """Re-run VLM tagging for one image (overwrites auto tags and vlm_caption)."""
    conn = get_connection(DEFAULT_DB_PATH)
    try:
        outcome = retag_image(conn, image_id, _vlm_client())
        if not outcome.ok:
            code = 404 if outcome.error == "image not found" else 400
            raise HTTPException(status_code=code, detail=outcome.error or "retag failed")
        conn.commit()
        row = conn.execute(
            "SELECT file_name, route_tag, vlm_caption FROM images WHERE image_id = ?",
            (image_id,),
        ).fetchone()
        tags = effective_tags(conn, image_id)
        tag_sources = tags_grouped_by_source(conn, image_id)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        conn.close()

    return {
        "image_id": image_id,
        "file_name": row["file_name"],
        "route_tag": row["route_tag"],
        "vlm_caption": row["vlm_caption"],
        "tags": tags,
        "tag_sources": {
            "auto": tag_sources["auto"],
            "filename": tag_sources["filename"],
            "auto_tagger": tag_sources["auto_tagger"],
            "auto_d1": tag_sources["auto_d1"],
            "inferred_ja": tag_sources["inferred_ja"],
            "manual_added": tag_sources["manual_added"],
        },
        "thinking_enabled": outcome.thinking_enabled,
        "reasoning_chars": outcome.reasoning_chars,
        "prompt_revision": PROMPT_REVISION,
    }


@app.get("/api/works/{work_id}/pages")
def list_work_pages(
    work_id: str,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    if not validate_work_id(work_id):
        raise HTTPException(status_code=400, detail="invalid work_id")

    conn = get_connection(DEFAULT_DB_PATH)
    try:
        result = get_work_pages(
            conn,
            work_id,
            limit=limit,
            offset=offset,
            has_thumbnail=_has_thumbnail,
        )
    finally:
        conn.close()

    if result is None:
        raise HTTPException(status_code=404, detail="work not found")
    return result


@app.get("/api/images/{image_id}/thumbnail")
def get_thumbnail(image_id: str) -> FileResponse:
    path = _thumb_paths(image_id).thumb
    if not path.is_file():
        raise HTTPException(status_code=404, detail="thumbnail not found")
    return FileResponse(path, media_type="image/webp")


@app.get("/api/images/{image_id}/preview")
def get_preview(image_id: str) -> FileResponse:
    path = _thumb_paths(image_id).preview
    if not path.is_file():
        raise HTTPException(status_code=404, detail="preview not found")
    return FileResponse(path, media_type="image/webp")


@app.get("/api/index/status")
def index_status() -> dict:
    conn = get_connection(DEFAULT_DB_PATH)
    try:
        embedded = conn.execute(
            "SELECT COUNT(*) FROM images WHERE status='active' AND indexed_at IS NOT NULL"
        ).fetchone()[0]
        stack = tag_stack_summary(conn)
        routes = tag_stack_by_route(conn)
    finally:
        conn.close()
    return {
        "images_active": stack["images_active"],
        "embedded": embedded,
        "vlm_pending": stack["jobs_pending"]["vlm_tag"],
        "tag_stack": stack,
        "by_route": {k: v["active"] for k, v in routes.items()},
        "tag_stack_by_route": routes,
    }
