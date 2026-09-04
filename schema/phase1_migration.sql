-- Phase 1 migration (additive — safe on existing Phase 0 DB)
-- Apply via: python scripts/migrate_db.py

CREATE TABLE IF NOT EXISTS image_metadata (
    image_id    TEXT PRIMARY KEY REFERENCES images(image_id) ON DELETE CASCADE,
    artist      TEXT,
    work_id     TEXT,
    posted_at   TEXT,
    source_url  TEXT,
    extra_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_image_metadata_work_id ON image_metadata(work_id);

CREATE TABLE IF NOT EXISTS index_jobs (
    job_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id    TEXT NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    job_type    TEXT NOT NULL
                CHECK (job_type IN ('vlm_tag', 'ocr', 'embedding', 'reindex')),
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    started_at  TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_index_jobs_pending ON index_jobs(status, job_type)
    WHERE status = 'pending';

CREATE VIRTUAL TABLE IF NOT EXISTS image_search USING fts5(
    image_id UNINDEXED,
    tags,
    ocr_text,
    tokenize = 'unicode61 remove_diacritics 0'
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO schema_migrations (version) VALUES ('phase1');
