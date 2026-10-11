"""Tag stack coverage and job queue counts for /api/index/status (M3)."""

from __future__ import annotations

import sqlite3


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def tag_stack_summary(conn: sqlite3.Connection) -> dict:
    active = _count(conn, "SELECT COUNT(*) FROM images WHERE status='active'")
    with_tagger = _count(
        conn,
        """
        SELECT COUNT(DISTINCT i.image_id) FROM images i
        WHERE i.status = 'active'
          AND EXISTS (
            SELECT 1 FROM image_tags t
            WHERE t.image_id = i.image_id AND t.source = 'auto_tagger'
          )
        """,
    )
    with_d1 = _count(
        conn,
        """
        SELECT COUNT(DISTINCT i.image_id) FROM images i
        WHERE i.status = 'active'
          AND EXISTS (
            SELECT 1 FROM image_tags t
            WHERE t.image_id = i.image_id AND t.source = 'auto_d1'
          )
        """,
    )
    tagger_jobs_pending = _count(
        conn,
        "SELECT COUNT(*) FROM index_jobs WHERE job_type='tagger_tag' AND status='pending'",
    )
    vlm_jobs_pending = _count(
        conn,
        "SELECT COUNT(*) FROM index_jobs WHERE job_type='vlm_tag' AND status='pending'",
    )
    return {
        "images_active": active,
        "with_auto_tagger": with_tagger,
        "with_auto_d1": with_d1,
        "missing_auto_tagger": max(0, active - with_tagger),
        "missing_auto_d1": max(0, active - with_d1),
        "jobs_pending": {
            "tagger_tag": tagger_jobs_pending,
            "vlm_tag": vlm_jobs_pending,
        },
    }


def tag_stack_by_route(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT
          COALESCE(i.route_tag, 'null') AS route_tag,
          COUNT(*) AS active,
          SUM(CASE WHEN EXISTS (
            SELECT 1 FROM image_tags t
            WHERE t.image_id = i.image_id AND t.source = 'auto_tagger'
          ) THEN 1 ELSE 0 END) AS with_tagger,
          SUM(CASE WHEN EXISTS (
            SELECT 1 FROM image_tags t
            WHERE t.image_id = i.image_id AND t.source = 'auto_d1'
          ) THEN 1 ELSE 0 END) AS with_d1
        FROM images i
        WHERE i.status = 'active'
        GROUP BY i.route_tag
        ORDER BY active DESC
        """
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        active = int(r["active"])
        wt = int(r["with_tagger"])
        wd = int(r["with_d1"])
        out[str(r["route_tag"])] = {
            "active": active,
            "with_auto_tagger": wt,
            "with_auto_d1": wd,
            "missing_auto_tagger": max(0, active - wt),
            "missing_auto_d1": max(0, active - wd),
        }
    return out
