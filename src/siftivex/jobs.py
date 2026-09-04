"""index_jobs queue: claim, process OCR/VLM jobs."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from siftivex.folder_rules import FolderRules, load_folder_rules
from siftivex.ingest import write_auto_ocr
from siftivex.ocr import ocr_engine_available, run_ocr
from siftivex.search_index import upsert_image_search
from siftivex.tags_db import (
    RETRY_TAG,
    apply_filename_tags,
    effective_tags,
    mark_image_missing,
    mark_vlm_retry_needed,
    replace_vlm_tags,
)
from siftivex.vlm import VlmClient, is_readable_image

MAX_JOB_ATTEMPTS = 3


@dataclass(frozen=True)
class JobRow:
    job_id: int
    image_id: str
    job_type: str
    attempts: int


@dataclass(frozen=True)
class JobResult:
    job_id: int
    image_id: str
    job_type: str
    ok: bool
    error: str | None = None


def fetch_pending_jobs(
    conn: sqlite3.Connection,
    *,
    job_type: str | None = None,
    limit: int = 10,
) -> list[JobRow]:
    if job_type:
        query = """
            SELECT job_id, image_id, job_type, attempts
            FROM index_jobs
            WHERE status = 'pending' AND job_type = ?
            ORDER BY job_id
            LIMIT ?
        """
        rows = conn.execute(query, (job_type, limit)).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT job_id, image_id, job_type, attempts
            FROM index_jobs
            WHERE status = 'pending'
            ORDER BY job_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        JobRow(job_id=r[0], image_id=r[1], job_type=r[2], attempts=r[3])
        for r in rows
    ]


def mark_job_running(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute(
        """
        UPDATE index_jobs
        SET status = 'running',
            started_at = COALESCE(started_at, datetime('now')),
            attempts = attempts + 1
        WHERE job_id = ?
        """,
        (job_id,),
    )


def mark_job_done(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute(
        """
        UPDATE index_jobs
        SET status = 'done', finished_at = datetime('now'), last_error = NULL
        WHERE job_id = ?
        """,
        (job_id,),
    )


def mark_job_failed(conn: sqlite3.Connection, job_id: int, error: str) -> None:
    row = conn.execute(
        "SELECT attempts FROM index_jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    attempts = row[0] if row else MAX_JOB_ATTEMPTS
    status = "failed" if attempts >= MAX_JOB_ATTEMPTS else "pending"
    conn.execute(
        """
        UPDATE index_jobs
        SET status = ?,
            finished_at = CASE WHEN ? = 'failed' THEN datetime('now') ELSE finished_at END,
            last_error = ?
        WHERE job_id = ?
        """,
        (status, status, error[:2000], job_id),
    )


def merge_vlm_ocr(conn: sqlite3.Connection, image_id: str, vlm_text: str) -> None:
    """Set auto_ocr from VLM only when dedicated OCR is empty."""
    if not vlm_text.strip():
        return
    row = conn.execute(
        "SELECT auto_ocr FROM image_ocr WHERE image_id = ?",
        (image_id,),
    ).fetchone()
    existing = (row[0] if row else "") or ""
    if existing.strip():
        return
    write_auto_ocr(conn, image_id, vlm_text.strip())


def resolve_ocr_engine(path: Path, folder_rules: FolderRules | None) -> str:
    if folder_rules:
        profile = folder_rules.match(path)
        if profile and profile.ocr_engine:
            return profile.ocr_engine
    return "paddle"


def process_ocr_job(
    conn: sqlite3.Connection,
    job: JobRow,
    *,
    folder_rules: FolderRules | None = None,
) -> JobResult:
    row = conn.execute(
        "SELECT source_path FROM images WHERE image_id = ? AND status = 'active'",
        (job.image_id,),
    ).fetchone()
    if not row:
        return JobResult(job.job_id, job.image_id, job.job_type, ok=False, error="image not found")

    path = Path(row[0])
    if not is_readable_image(path):
        mark_image_missing(conn, job.image_id)
        return JobResult(job.job_id, job.image_id, job.job_type, ok=False, error="missing image")

    engine = resolve_ocr_engine(path, folder_rules)
    if not ocr_engine_available(engine):
        return JobResult(
            job.job_id,
            job.image_id,
            job.job_type,
            ok=False,
            error=f"OCR engine {engine!r} not installed",
        )

    text = run_ocr(path, engine)
    write_auto_ocr(conn, job.image_id, text)
    upsert_image_search(conn, job.image_id)
    return JobResult(job.job_id, job.image_id, job.job_type, ok=True)


def process_vlm_job(conn: sqlite3.Connection, job: JobRow, client: VlmClient) -> JobResult:
    row = conn.execute(
        "SELECT source_path, file_name FROM images WHERE image_id = ? AND status = 'active'",
        (job.image_id,),
    ).fetchone()
    if not row:
        return JobResult(job.job_id, job.image_id, job.job_type, ok=False, error="image not found")

    path = Path(row[0])
    filename = row[1]
    if not is_readable_image(path):
        mark_image_missing(conn, job.image_id)
        return JobResult(job.job_id, job.image_id, job.job_type, ok=False, error="missing image")

    filename_tags = apply_filename_tags(conn, job.image_id, filename)
    result = client.tag_image(path, priority_tags=filename_tags)
    replace_vlm_tags(conn, job.image_id, result.namespace_tags, result.flat_tags)
    conn.execute(
        "UPDATE images SET vlm_caption = ?, updated_at = datetime('now') WHERE image_id = ?",
        (result.caption, job.image_id),
    )
    if not result.namespace_tags and not result.flat_tags:
        conn.execute(
            "INSERT OR IGNORE INTO image_tags (image_id, tag, source) VALUES (?, ?, 'auto')",
            (job.image_id, "未分類"),
        )
    merge_vlm_ocr(conn, job.image_id, result.ocr_text)
    upsert_image_search(conn, job.image_id)
    _ = effective_tags(conn, job.image_id)
    return JobResult(job.job_id, job.image_id, job.job_type, ok=True)


def run_jobs(
    conn: sqlite3.Connection,
    *,
    job_type: str | None = None,
    limit: int = 10,
    folder_rules: FolderRules | None = None,
    vlm_client: VlmClient | None = None,
) -> list[JobResult]:
    jobs = fetch_pending_jobs(conn, job_type=job_type, limit=limit)
    results: list[JobResult] = []

    for job in jobs:
        mark_job_running(conn, job.job_id)
        conn.commit()

        try:
            if job.job_type == "ocr":
                outcome = process_ocr_job(conn, job, folder_rules=folder_rules)
            elif job.job_type == "vlm_tag":
                if vlm_client is None:
                    outcome = JobResult(
                        job.job_id, job.image_id, job.job_type, ok=False, error="VLM client not configured"
                    )
                else:
                    outcome = process_vlm_job(conn, job, vlm_client)
            else:
                outcome = JobResult(
                    job.job_id, job.image_id, job.job_type, ok=False, error=f"unsupported job_type {job.job_type!r}"
                )
        except Exception as exc:
            outcome = JobResult(job.job_id, job.image_id, job.job_type, ok=False, error=str(exc))
            if job.job_type == "vlm_tag":
                mark_vlm_retry_needed(conn, job.image_id)

        if outcome.ok:
            mark_job_done(conn, job.job_id)
        else:
            mark_job_failed(conn, job.job_id, outcome.error or "unknown error")
        conn.commit()
        results.append(outcome)

    return results
