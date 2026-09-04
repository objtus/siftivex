#!/usr/bin/env python3
"""Migrate image_tags to allow source='filename'."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH  # noqa: E402

SQL = """
CREATE TABLE image_tags_new (
    image_id    TEXT    NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    tag         TEXT    NOT NULL,
    source      TEXT    NOT NULL
                CHECK (source IN ('auto', 'filename', 'manual_added', 'manual_removed')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (image_id, tag, source)
);

INSERT INTO image_tags_new SELECT * FROM image_tags;
DROP TABLE image_tags;
ALTER TABLE image_tags_new RENAME TO image_tags;

CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag);
CREATE INDEX IF NOT EXISTS idx_image_tags_source ON image_tags(image_id, source);
"""


def main() -> int:
    conn = get_connection()
    try:
        conn.executescript(SQL)
        conn.commit()
    finally:
        conn.close()
    print(f"Migrated image_tags (filename source) in {DEFAULT_DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
