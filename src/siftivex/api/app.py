"""FastAPI application skeleton."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from siftivex.db import get_connection
from siftivex.paths import DEFAULT_DB_PATH, DEFAULT_THUMBNAILS_DIR
from siftivex.tags_db import effective_tags
from siftivex.thumbnails import ThumbnailPaths, thumbnail_dir

app = FastAPI(title="Siftivex", version="0.1.0")


def _thumb_paths(image_id: str) -> ThumbnailPaths:
    base = thumbnail_dir(image_id, DEFAULT_THUMBNAILS_DIR)
    return ThumbnailPaths(thumb=base / "thumb.webp", preview=base / "preview.webp")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
        ocr = conn.execute(
            "SELECT COALESCE(manual_ocr, auto_ocr, '') AS text FROM image_ocr WHERE image_id = ?",
            (image_id,),
        ).fetchone()
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
        "ocr_text": ocr["text"] if ocr else "",
        "has_thumbnail": thumbs.thumb.is_file(),
        "has_preview": thumbs.preview.is_file(),
    }


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
        total = conn.execute("SELECT COUNT(*) FROM images WHERE status='active'").fetchone()[0]
        embedded = conn.execute(
            "SELECT COUNT(*) FROM images WHERE status='active' AND indexed_at IS NOT NULL"
        ).fetchone()[0]
        vlm_pending = conn.execute(
            "SELECT COUNT(*) FROM index_jobs WHERE job_type='vlm_tag' AND status='pending'"
        ).fetchone()[0]
        by_route = conn.execute(
            """
            SELECT route_tag, COUNT(*) AS n
            FROM images WHERE status='active'
            GROUP BY route_tag ORDER BY n DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return {
        "images_active": total,
        "embedded": embedded,
        "vlm_pending": vlm_pending,
        "by_route": {r["route_tag"] or "null": r["n"] for r in by_route},
    }
