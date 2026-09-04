"""Parse pixiv downloader-style filenames (date_id_user_title_tags)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# `id_4826` または `_4826`（Gallery-Dl 等）
_WORK_ID = r"(?:id_|_)(?P<work_id>\d+)"

# PixivUtil2 / Gallery-Dl: `_tags_` あり
PIXIV_WITH_TAGS_RE = re.compile(
    r"^date_(?P<posted_at>\d{4}-\d{2}-\d{2})"
    + _WORK_ID
    + r"(?:_p(?P<page>\d+))?"
    r"user_(?P<artist>.+?)"
    r"title_(?P<title>.+?)"
    r"_tags_(?P<pixiv_tags>.+?)"
    r"\.(?P<ext>[^.]+)$",
    re.UNICODE,
)

# 一部ダウンローダー: `title_xxx_タグ1,タグ2.ext`（tags_ キーワードなし）
PIXIV_NO_TAGS_KEYWORD_RE = re.compile(
    r"^date_(?P<posted_at>\d{4}-\d{2}-\d{2})"
    + _WORK_ID
    + r"(?:_p(?P<page>\d+))?"
    r"user_(?P<artist>.+?)"
    r"title_(?P<title>.+?)_(?P<pixiv_tags>.+?)"
    r"\.(?P<ext>[^.]+)$",
    re.UNICODE,
)

# パース不能な長文件名向け: work_id / page / ext のみ抽出
PIXIV_FALLBACK_RE = re.compile(
    r"^date_(?P<posted_at>\d{4}-\d{2}-\d{2})"
    + _WORK_ID
    + r"(?:_p(?P<page>\d+))?"
    r".*\.(?P<ext>[^.]+)$",
    re.UNICODE,
)

SIDECAR_SUFFIX = ".pixiv.json"


@dataclass(frozen=True)
class PixivFilenameMeta:
    original_filename: str
    posted_at: str
    work_id: str
    page: int | None
    artist: str
    title: str
    pixiv_tags: list[str]
    ext: str
    parse_mode: str = "full"

    @property
    def source_url(self) -> str:
        return f"https://www.pixiv.net/artworks/{self.work_id}"

    def short_filename(self) -> str:
        if self.page is not None:
            return f"{self.work_id}_p{self.page}.{self.ext}"
        return f"{self.work_id}.{self.ext}"

    def sidecar_filename(self) -> str:
        return f"{Path(self.short_filename()).stem}{SIDECAR_SUFFIX}"

    def to_sidecar_dict(self) -> dict:
        data = {
            "version": 1,
            "original_filename": self.original_filename,
            "posted_at": self.posted_at,
            "work_id": self.work_id,
            "page": self.page,
            "artist": self.artist,
            "title": self.title,
            "pixiv_tags": self.pixiv_tags,
            "source_url": self.source_url,
        }
        if self.parse_mode != "full":
            data["parse_mode"] = self.parse_mode
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_sidecar_dict(), ensure_ascii=False, indent=2) + "\n"


def _meta_from_match(
    filename: str,
    groups: dict[str, str | None],
    *,
    parse_mode: str,
) -> PixivFilenameMeta:
    tags_raw = groups.get("pixiv_tags") or ""
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    page = groups.get("page")
    return PixivFilenameMeta(
        original_filename=filename,
        posted_at=groups["posted_at"] or "",
        work_id=groups["work_id"] or "",
        page=int(page) if page is not None else None,
        artist=groups.get("artist") or "",
        title=groups.get("title") or "",
        pixiv_tags=tags,
        ext=groups["ext"] or "",
        parse_mode=parse_mode,
    )


def parse_pixiv_filename(filename: str) -> PixivFilenameMeta | None:
    """Return metadata if filename matches pixiv downloader format."""
    for pattern, mode in (
        (PIXIV_WITH_TAGS_RE, "full"),
        (PIXIV_NO_TAGS_KEYWORD_RE, "no_tags_keyword"),
    ):
        match = pattern.match(filename)
        if match:
            return _meta_from_match(filename, match.groupdict(), parse_mode=mode)
    return None


def parse_pixiv_filename_fallback(filename: str) -> PixivFilenameMeta | None:
    """Minimal metadata when full parse fails (long filenames)."""
    match = PIXIV_FALLBACK_RE.match(filename)
    if not match:
        return None
    return _meta_from_match(
        filename,
        {**match.groupdict(), "artist": "", "title": "", "pixiv_tags": ""},
        parse_mode="fallback",
    )


def filename_byte_length(name: str) -> int:
    return len(name.encode("utf-8"))
