"""Pixiv work (multi-page) grouping for API responses."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Callable

WORK_ID_PATTERN = re.compile(r"^\d+$")


def parse_extra_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def page_from_extra(extra: dict) -> int | None:
    page = extra.get("page")
    if page is None:
        return None
    if isinstance(page, int):
        return page
    try:
        return int(page)
    except (TypeError, ValueError):
        return None


def validate_work_id(work_id: str) -> bool:
    return bool(WORK_ID_PATTERN.fullmatch(work_id))


def _page_sort_key(page: int | None, file_name: str) -> tuple[int, int, str]:
    if page is None:
        return (1, 0, file_name)
    return (0, page, file_name)


def fetch_work_page_rows(conn: sqlite3.Connection, work_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT i.image_id, i.file_name, i.width, i.height,
               m.artist, m.posted_at, m.source_url, m.extra_json
        FROM image_metadata m
        JOIN images i ON i.image_id = m.image_id
        WHERE m.work_id = ? AND i.status = 'active'
        """,
        (work_id,),
    ).fetchall()


def sort_work_pages(rows: list[sqlite3.Row]) -> list[tuple[sqlite3.Row, int | None, dict]]:
    parsed: list[tuple[sqlite3.Row, int | None, dict]] = []
    for row in rows:
        extra = parse_extra_json(row["extra_json"])
        parsed.append((row, page_from_extra(extra), extra))
    parsed.sort(key=lambda item: _page_sort_key(item[1], item[0]["file_name"]))
    return parsed


def _work_title(sorted_pages: list[tuple[sqlite3.Row, int | None, dict]]) -> str | None:
    for _, _, extra in sorted_pages:
        title = extra.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return None


def _title_from_extra(extra: dict) -> str | None:
    title = extra.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def image_metadata_for_image(
    conn: sqlite3.Connection,
    image_id: str,
) -> dict | None:
    """Return structured metadata for an image when present (any route)."""
    meta = conn.execute(
        """
        SELECT m.work_id, m.artist, m.posted_at, m.source_url, m.extra_json
        FROM image_metadata m
        JOIN images i ON i.image_id = m.image_id
        WHERE m.image_id = ? AND i.status = 'active'
        """,
        (image_id,),
    ).fetchone()
    if meta is None:
        return None

    extra = parse_extra_json(meta["extra_json"])
    return {
        "work_id": meta["work_id"],
        "title": _title_from_extra(extra),
        "artist": meta["artist"],
        "posted_at": meta["posted_at"],
        "source_url": meta["source_url"],
        "page": page_from_extra(extra),
    }


def page_item_dict(
    row: sqlite3.Row,
    page: int | None,
    *,
    has_thumbnail: Callable[[str], bool] | None = None,
) -> dict:
    image_id = row["image_id"]
    return {
        "image_id": image_id,
        "page": page,
        "file_name": row["file_name"],
        "width": row["width"],
        "height": row["height"],
        "has_thumbnail": has_thumbnail(image_id) if has_thumbnail else False,
    }


def get_work_pages(
    conn: sqlite3.Connection,
    work_id: str,
    *,
    limit: int = 200,
    offset: int = 0,
    has_thumbnail: Callable[[str], bool] | None = None,
) -> dict | None:
    rows = fetch_work_page_rows(conn, work_id)
    if not rows:
        return None

    sorted_pages = sort_work_pages(rows)
    page_count = len(sorted_pages)
    slice_pages = sorted_pages[offset : offset + limit]
    first_row = sorted_pages[0][0]

    return {
        "work_id": work_id,
        "title": _work_title(sorted_pages),
        "artist": first_row["artist"],
        "posted_at": first_row["posted_at"],
        "source_url": first_row["source_url"],
        "page_count": page_count,
        "limit": limit,
        "offset": offset,
        "items": [
            page_item_dict(row, page, has_thumbnail=has_thumbnail) for row, page, _ in slice_pages
        ],
    }


def work_context_for_image(
    conn: sqlite3.Connection,
    image_id: str,
) -> dict | None:
    meta = conn.execute(
        """
        SELECT m.work_id, m.artist, m.posted_at, m.source_url, m.extra_json
        FROM image_metadata m
        JOIN images i ON i.image_id = m.image_id
        WHERE m.image_id = ? AND i.status = 'active'
        """,
        (image_id,),
    ).fetchone()
    if meta is None or not meta["work_id"]:
        return None

    work_id = meta["work_id"]
    sorted_pages = sort_work_pages(fetch_work_page_rows(conn, work_id))
    if len(sorted_pages) <= 1:
        return None

    extra = parse_extra_json(meta["extra_json"])
    current_page = page_from_extra(extra)
    image_ids = [row["image_id"] for row, _, _ in sorted_pages]
    try:
        page_index = image_ids.index(image_id)
    except ValueError:
        page_index = 0

    return {
        "work_id": work_id,
        "title": _work_title(sorted_pages),
        "artist": meta["artist"],
        "posted_at": meta["posted_at"],
        "source_url": meta["source_url"],
        "page": current_page,
        "page_index": page_index,
        "page_count": len(sorted_pages),
        "prev_image_id": image_ids[page_index - 1] if page_index > 0 else None,
        "next_image_id": image_ids[page_index + 1] if page_index + 1 < len(image_ids) else None,
    }
