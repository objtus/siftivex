-- Widen image_tags.source for tag stack (auto_tagger, auto_d1, inferred_ja)

CREATE TABLE image_tags_new (
    image_id    TEXT    NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    tag         TEXT    NOT NULL,
    source      TEXT    NOT NULL
                CHECK (source IN (
                    'auto', 'filename', 'manual_added', 'manual_removed',
                    'auto_tagger', 'auto_d1', 'inferred_ja'
                )),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (image_id, tag, source)
);

INSERT INTO image_tags_new SELECT * FROM image_tags;
DROP TABLE image_tags;
ALTER TABLE image_tags_new RENAME TO image_tags;

CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag);
CREATE INDEX IF NOT EXISTS idx_image_tags_source ON image_tags(image_id, source);
