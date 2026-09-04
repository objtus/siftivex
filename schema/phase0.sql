-- Phase 0 最小スキーマ
-- 参照: docs/specs/data-model.md

CREATE TABLE IF NOT EXISTS images (
    image_id        TEXT PRIMARY KEY,
    content_hash    TEXT NOT NULL UNIQUE,
    source_path     TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    file_size       INTEGER,
    width           INTEGER,
    height          INTEGER,
    mime_type       TEXT,
    phash           TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'missing', 'archived')),
    route_tag       TEXT,
    vlm_caption     TEXT,
    exif_datetime   TEXT,
    file_mtime      TEXT,
    indexed_at      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE INDEX IF NOT EXISTS idx_images_route_tag ON images(route_tag);
CREATE INDEX IF NOT EXISTS idx_images_source_path ON images(source_path);

CREATE TABLE IF NOT EXISTS image_tags (
    image_id    TEXT    NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    tag         TEXT    NOT NULL,
    source      TEXT    NOT NULL
                CHECK (source IN ('auto', 'manual_added', 'manual_removed')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (image_id, tag, source)
);

CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag);
CREATE INDEX IF NOT EXISTS idx_image_tags_source ON image_tags(image_id, source);

CREATE TABLE IF NOT EXISTS image_ocr (
    image_id    TEXT PRIMARY KEY REFERENCES images(image_id) ON DELETE CASCADE,
    auto_ocr    TEXT,
    manual_ocr  TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('started', 'done', 'failed', 'skipped')),
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    details     TEXT
);
