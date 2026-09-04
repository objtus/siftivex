# データモデル

> **状態**: 草案（Phase 0 最小版 + Phase 1 拡張を含む）
> **参照**: [blueprint.md](../../blueprint.md) §用語集, §タグ・OCRの手動修正, §対応ファイル形式

## 概要

SQLite をメタデータの正本とし、LanceDB を embedding ベクトルの保存先とする。

| ストア | 役割 | Phase |
|---|---|---|
| SQLite | 画像メタデータ、タグ、OCR、アルバム、ジョブキュー | 0〜 |
| SQLite FTS5 | タグ・OCR の全文検索 | 1〜 |
| LanceDB | CLIP embedding ベクトル + ANN 検索 | 0〜 |

## 識別子

### `image_id`（主キー）

| 項目 | 値 |
|---|---|
| 形式 | `img_` + BLAKE3 hex の先頭 16 文字 |
| 例 | `img_a1b2c3d4e5f67890` |
| 生成 | deterministic（ファイル内容から導出） |

→ 決定経緯: [OQ-005](../open-questions.md#oq-005-image_id-の生成規則)

### `content_hash`（完全同一性）

| 項目 | 値 |
|---|---|
| 形式 | BLAKE3-256 hex 全文（64 文字） |
| 制約 | `UNIQUE NOT NULL` |
| 用途 | 重複検出、移動検出、image_id 導出の元 |

### `phash`（知覚的類似）

| 項目 | 値 |
|---|---|
| 形式 | 64 bit integer を hex 文字列化（16 文字） |
| 用途 | 重複候補グルーピング（Phase 4、優先度低） |
| Phase | 1 以降（スキーマには先行定義） |

### その他 ID

| ID | 形式 | 備考 |
|---|---|---|
| `album_id` | `alb_` + name の slug（小文字、スペース→`-`） | 例: `alb_参考資料` |
| `job_id` | `INTEGER AUTOINCREMENT` | 内部用 |

---

## ER 概要

```
images ─┬─ image_tags (1:N)
        ├─ image_ocr  (1:1)
        ├─ image_metadata (1:1, Phase 1)
        └─ album_members (N:M via albums)

index_jobs ── images (N:1)

LanceDB embeddings ── images (1:1, image_id で結合)
image_search (FTS5) ── images (1:1, image_id で結合)
```

---

## テーブル定義

### `images`

画像の基本メタデータ。Phase 0 から使用。

```sql
CREATE TABLE images (
    image_id        TEXT PRIMARY KEY,           -- img_<16 hex chars>
    content_hash    TEXT NOT NULL UNIQUE,       -- BLAKE3-256 full hex
    source_path     TEXT NOT NULL,              -- 現在の絶対パス
    file_name       TEXT NOT NULL,
    file_size       INTEGER,                    -- bytes
    width           INTEGER,
    height          INTEGER,
    mime_type       TEXT,                       -- image/jpeg 等
    phash           TEXT,                       -- Phase 4
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'missing', 'archived')),
    route_tag       TEXT,                       -- route/pixiv 等
    vlm_caption     TEXT,                       -- VLM 生成キャプション原文
    exif_datetime   TEXT,                       -- ISO 8601
    file_mtime      TEXT,                       -- ISO 8601
    indexed_at      TEXT,                       -- 最終インデックス完了日時
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_images_status ON images(status);
CREATE INDEX idx_images_route_tag ON images(route_tag);
CREATE INDEX idx_images_source_path ON images(source_path);
```

**status の意味**

| 値 | 意味 |
|---|---|
| `active` | 通常表示対象 |
| `missing` | 監視フォルダにファイル不在（タグ等は保持） |
| `archived` | 非表示（物理削除しない） |

**取り込み時の upsert**

```sql
INSERT INTO images (image_id, content_hash, source_path, file_name, …)
VALUES (?, ?, ?, ?, …)
ON CONFLICT(content_hash) DO UPDATE SET
    source_path = excluded.source_path,
    file_name   = excluded.file_name,
    file_mtime  = excluded.file_mtime,
    status      = 'active',          -- missing から復帰
    updated_at  = datetime('now');
```

---

### `image_tags`

差分レイヤー方式。1 画像に同一タグの複数 source レコードがありうる。

```sql
CREATE TABLE image_tags (
    image_id    TEXT    NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    tag         TEXT    NOT NULL,   -- 正規化済み。例: "種類/イラスト", "セーラー服"
    source      TEXT    NOT NULL
                CHECK (source IN ('auto', 'manual_added', 'manual_removed')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (image_id, tag, source)
);

CREATE INDEX idx_image_tags_tag ON image_tags(tag);
CREATE INDEX idx_image_tags_source ON image_tags(image_id, source);
```

**表示タグの導出**

```
effective_tags(image_id) =
    { tag | (source IN ('auto', 'manual_added')) }
  − { tag | source = 'manual_removed' }
```

SQL 表現:

```sql
SELECT tag FROM image_tags
WHERE image_id = ?
  AND source IN ('auto', 'manual_added')
  AND tag NOT IN (
    SELECT tag FROM image_tags
    WHERE image_id = ? AND source = 'manual_removed'
  );
```

**VLM 再実行時**

```sql
DELETE FROM image_tags WHERE image_id = ? AND source = 'auto';
-- 新しい auto タグを INSERT
```

`manual_added` / `manual_removed` は削除しない。

**タグ正規化ルール**

- 名前空間タグ: `namespace/value` 形式（スラッシュ区切り、末尾スラッシュなし）
- フラットタグ: 前後空白除去、内部連続空白は単一スペースに
- 大文字小文字: 保存時はそのまま。検索時は FTS5 の tokenize に委ねる

---

### `image_ocr`

```sql
CREATE TABLE image_ocr (
    image_id    TEXT PRIMARY KEY REFERENCES images(image_id) ON DELETE CASCADE,
    auto_ocr    TEXT,
    manual_ocr  TEXT,               -- 存在すればこちらを優先表示
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**表示テキスト**: `COALESCE(manual_ocr, auto_ocr, '')`

---

### `albums` / `album_members`

Phase 1 以降。Phase 0 では作成不要。

```sql
CREATE TABLE albums (
    album_id    TEXT PRIMARY KEY,   -- alb_<slug>
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE album_members (
    album_id    TEXT NOT NULL REFERENCES albums(album_id) ON DELETE CASCADE,
    image_id    TEXT NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    sort_order  INTEGER,            -- NULL = 追加日順
    added_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (album_id, image_id)
);

CREATE INDEX idx_album_members_image ON album_members(image_id);
```

---

### `image_metadata`

ファイル名パーサー由来の構造化メタデータ。Phase 1 以降。

```sql
CREATE TABLE image_metadata (
    image_id    TEXT PRIMARY KEY REFERENCES images(image_id) ON DELETE CASCADE,
    artist      TEXT,
    work_id     TEXT,
    posted_at   TEXT,               -- ISO 8601
    source_url  TEXT,
    extra_json  TEXT                -- パーサー固有フィールド（JSON）
);
```

---

### `index_jobs`

VLM タグ付け等の非同期ジョブキュー。Phase 1 本格運用、Phase 0 では簡易利用可。

```sql
CREATE TABLE index_jobs (
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

CREATE INDEX idx_index_jobs_pending ON index_jobs(status, job_type)
    WHERE status = 'pending';
```

---

## FTS5 仮想テーブル

Phase 1 以降。タグ・OCR の全文検索用。

```sql
CREATE VIRTUAL TABLE image_search USING fts5(
    image_id UNINDEXED,
    tags,           -- effective_tags をスペース区切り結合
    ocr_text,
    tokenize = 'unicode61 remove_diacritics 0'
);
```

**更新タイミング**: タグまたは OCR が変更されたとき、アプリケーション層で effective_tags と ocr_text を再計算して upsert。

Phase 0 では FTS5 なし（件数が少ないため LIKE / アプリ側フィルタで足りる）。

---

## LanceDB スキーマ

Phase 0 から使用。Python 側での定義例:

```python
# テーブル名: embeddings
# カラム:
#   image_id   : str       -- SQLite images.image_id と一致
#   vector     : float32[dim]  -- CLIP モデル依存（例: 768 or 1024）
#   model      : str       -- 例: "siglip-so400m-patch14-384"
#   created_at : str       -- ISO 8601
```

**検索時の結合**: LanceDB で ANN 検索 → 返却された `image_id` リストで SQLite をフィルタ（タグ/album/status 条件）。

**モデル変更時**: `model` カラムで区別し、全件再 embedding。旧ベクトルは削除。

---

## Phase 0 最小スキーマ

Phase 0 で実際に作成するテーブル:

| テーブル | 用途 |
|---|---|
| `images` | 基本メタデータ |
| `image_tags` | VLM タグ（source=`auto` のみ） |
| `image_ocr` | OCR 結果（source 相当は auto_ocr のみ） |

LanceDB `embeddings` テーブル。

**Phase 0 では作らないもの**: `albums`, `image_metadata`, `index_jobs`（任意）, FTS5

---

## ファイル配置

| ファイル | 用途 |
|---|---|
| `data/siftivex.db` | SQLite 本体（gitignore） |
| `data/lance/` | LanceDB データ（gitignore） |
| `data/phase0/manifest.json` | 検証用データセット（gitignore） |

---

## 関連ドキュメント

- [tags.md](tags.md) — タグの意味論・名前空間
- [query-language.md](query-language.md) — FTS5 への変換
- [indexing.md](indexing.md) — 書き込みタイミング
- [open-questions.md](../open-questions.md) — OQ-005 決定記録
