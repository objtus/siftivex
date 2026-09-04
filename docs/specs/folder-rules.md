# フォルダルール・取り込みプロファイル

> **参照**: [blueprint.md](../../blueprint.md) §取り込みルート・フォルダルール

## 概要

フォルダパス単位の取り込みルール。自動付与タグとメタデータ抽出（sidecar / ファイル名パーサー）を定義する。
設定は `config/folder_rules.yaml`（gitignore）に保持。テンプレートは [folder_rules.yaml.example](../../config/folder_rules.yaml.example)。

## 設定ファイル

| ファイル | 内容 |
|---|---|
| `folder_rules.yaml` | フォルダパス → プロファイルのマッピング |
| `config/parsers/*.yaml` | under.iphone 等のパーサー定義（YAML） |
| `src/siftivex/pixiv_filename.py` | pixiv パーサー実装（コード） |

パスマッチング: **最長 prefix 一致**（より具体的なルールが優先）。

## プロファイル構造

```yaml
profiles:
  pixiv_bookmarks:
    route_tag: route/pixiv
    metadata: pixiv_hybrid          # sidecar 優先 → ファイル名パーサー
    ocr_engine: manga
    fixed_tags: []

  under_iphone:
    route_tag: route/under-iphone
    parser: under_iphone_legacy_v1
    ocr_engine: paddle
    fixed_tags: []

rules:
  - path_prefix: /srv/siftivex-archive/pixiv
    profile: pixiv_bookmarks
  - path_prefix: /srv/siftivex-archive/under.iphone
    profile: under_iphone
```

---

## pixiv（OQ-002 resolved）

2026-09-04 同期完了。~36,569 メディア（jpg/png/gif/webm）、~46 GB。

### メタデータ解決順（`pixiv_hybrid`）

同一フォルダ内の画像に対し、**上から最初にマッチした方法**を使う。

| 優先 | 条件 | ソース | 備考 |
|---|---|---|---|
| 1 | `{stem}.pixiv.json` が隣接 | sidecar JSON | 長文件名移行後（~8,118 件） |
| 2 | ファイル名が pixiv ダウンローダー形式 | `parse_pixiv_filename()` | 旧形式 `date_*`（~28,451 件） |
| 3 | 上記いずれも不可 | — | `route/pixiv` のみ。メタデータなし |

sidecar 形式（`scripts/pixiv_migrate_standalone.py` が生成）:

```json
{
  "version": 1,
  "original_filename": "date_2007-09-17id_4826_p0user_…",
  "posted_at": "2007-09-17",
  "work_id": "4826",
  "page": 0,
  "artist": "…",
  "title": "…",
  "pixiv_tags": ["…"],
  "source_url": "https://www.pixiv.net/artworks/4826"
}
```

### ファイル名形式（legacy パーサー）

実装: `src/siftivex/pixiv_filename.py`

| 形式 | 例 | 備考 |
|---|---|---|
| 標準（`_tags_` あり） | `date_2007-09-17id_4826_p0user_…title_…_tags_博麗霊夢,東方.jpg` | PixivUtil2 系 |
| tags キーワードなし | `date_2023-08-06id_110577126_p29user_…title_…_アイドルマスター….png` | `_tags_` 省略 |
| work_id 区切り `_` | `date_2024-12-06_124937780_p3user_….png` | `id_` 省略 |
| 短名（移行後） | `4826_p0.jpg` | sidecar とセット |

抽出フィールド: `posted_at`, `work_id`, `page`, `artist`, `title`, `pixiv_tags`, `source_url`

### 取り込み時のスキップ

| 対象 | 理由 |
|---|---|
| `*.pixiv.json` | sidecar。画像レコードは隣接メディアから作成 |
| `result-total*` / `*.csv` / `*.py` | エクスポート・作業ファイル（[syncthing-pixiv.stignore](../../config/syncthing-pixiv.stignore) も参照） |
| 旧 `date_*` で短名 `{work_id}_p{n}.ext` が既に DB 登録済み | 移行重複（~9 件）。短名を正とする |

### OCR

`ocr_engine: manga` → manga-ocr（[indexing.md](indexing.md) ハイブリッド方針）

---

## under.iphone（OQ-003 resolved）

`config/parsers/under_iphone_legacy_v1.yaml` — `{id}_{tag}-{tag}.ext`

`ocr_engine: paddle`

---

### web 収集（パーサーなし — 未同期）

`route/web` タグのみ自動付与。ファイル名からのメタデータ抽出なし。

**未同期・見込み ~30,000–40,000 枚**（Twitter / Google / Pinterest 等）。  
→ [paths.yaml.example](../../config/paths.yaml.example) `archives.web_misc`、全体規模は [phase-1-prep.md](../decisions/phase-1-prep.md)

---

## 関連ドキュメント

- [tags.md](tags.md) — route タグの定義
- [indexing.md](indexing.md) — 取り込み時の適用タイミング
- [data-model.md](data-model.md) — 抽出メタデータの保存先（`image_metadata`）
- [setup/windows-sync.md](../setup/windows-sync.md) — Syncthing・長文件名移行
