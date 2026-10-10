-- Extend index_jobs.job_type for tagger batch (tag stack migration)
-- Rebuild table to widen CHECK constraint.

CREATE TABLE IF NOT EXISTS index_jobs_new (
    job_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id    TEXT NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    job_type    TEXT NOT NULL
                CHECK (job_type IN ('vlm_tag', 'tagger_tag', 'ocr', 'embedding', 'reindex')),
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    started_at  TEXT,
    finished_at TEXT
);

INSERT INTO index_jobs_new
SELECT job_id, image_id, job_type, status, attempts, last_error, created_at, started_at, finished_at
FROM index_jobs;

DROP TABLE index_jobs;

ALTER TABLE index_jobs_new RENAME TO index_jobs;

CREATE INDEX IF NOT EXISTS idx_index_jobs_pending ON index_jobs(status, job_type)
    WHERE status = 'pending';
