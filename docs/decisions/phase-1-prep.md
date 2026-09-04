# Phase 1 着手前の決定事項

> **更新**: 2026-09-04（pixiv 同期完了・規模確定後）
> **目的**: Phase 1 実装前に決めた方針を1か所に集約（平易な説明付き）

## 決定チェックリスト（確定）

| # | 項目 | 決定 | メモ |
|---|---|---|---|
| 1 | OCR ハイブリッド | ✅ dedicated + VLM `ocr_text`、dedicated 優先 | [indexing.md §OCR](../specs/indexing.md) |
| 2 | OCR ルーティング | **B** | `folder_rules.yaml` の `ocr_engine` で指定 |
| 3 | 重複時 upsert | **A** | path 更新のみ。再 embed / 再 OCR / 再 VLM しない |
| 4 | サムネイル | **A** | 256 / 1280 WebP。**原寸が小さければ拡大しない** |
| 5 | CLIP embedding | **C** | Phase 1 は ViT-B-32 継続。SigLIP は Phase 2 |
| 6 | VLM キュー | **A** | `index_jobs` + n8n 定期実行 |
| 7 | ファイル消失・移動 | **A** | 1日1回スキャン → missing / 移動検出 |
| 8 | folder-rules | **B** 段階的 | Phase 1: under.iphone + pixiv。以降ルート追加 |
| 9 | 身体部位 namespace | **A** 見送り | flat 継続。namespace 設計自体は Phase 1〜2 で検討可 |
| 10 | 未分類 / 要再タグ | **実装準拠** | Phase 0 実装どおり（下記） |
| 11 | DB テーブル | **A** + **`image_metadata`（C）** | pixiv 含むため metadata も Phase 1 |
| 12 | FTS5 | **A** | Phase 1 から `image_search` 更新 |
| 13 | n8n | **A** | poll + 初回手動バッチ |
| 14 | 初回投入順 | **B** | 両アーカイブを Phase 1 対象。実行順: under.iphone → pixiv |

---

## わかりやすく（各項目の意味）

### サムネイル（#4）— 「小さい原寸は変換不要？」

**A の意味は「無理に拡大しない」です。**

| 原寸 | thumb (256) | preview (1280) |
|---|---|---|
| 4000×3000 | 長辺 256 に縮小 | 長辺 1280 に縮小 |
| 800×600 | **800×600 のまま**（拡大しない） | **800×600 のまま** |
| 200×200 | **200×200 のまま** | **200×200 のまま** |

小さい画像を 256px に引き伸ばすとボケるので、ターゲットより小さい場合はそのサイズで WebP 保存（または参照のみ）します。

### 重複 upsert（#3）

同じ画像（`content_hash` 一致）が別パスで再登場したとき:

- DB のパス情報だけ更新
- embedding 等は**やり直さない**（移動・再同期で十分）

### CLIP（#5 C）

- **今**: Phase 0 と同じ ViT-B-32（速い・検証済み）
- **後**: Phase 2 で SigLIP 等に変えたら全件再 embed

### folder-rules（#8 B）

一度に全部のフォルダルールを作らず、**Phase 1 は under.iphone + pixiv だけ**有効化。iCloud 等は後から追加。

### 未分類 / 要再タグ（#10）

| タグ | いつ付くか |
|---|---|
| `未分類` | VLM は動いたがタグが空 |
| `要再タグ` | VLM が JSON パース等で失敗 |

レビュー HTML では `tag:要再タグ OR tag:未分類` で絞り込み。

### `image_metadata`（#11 — OQ-010）

pixiv には **作者名・作品 ID・タグ** がファイル名 / sidecar に入っている。Phase 1 で専用テーブルに保存し、検索・表示に使う（**C**）。

---

## アーカイブ規模

### 同期済み（2026-09-04）

| アーカイブ | メディア枚数 | 容量 | 状態 |
|---|---|---|---|
| under.iphone | **3,994** | 3.5 GB | 同期済 |
| pixiv | **36,560** | ~46 GB | 同期済 |
| **小計** | **~40,554** | ~50 GB | Phase 1 初回投入対象 |

pixiv 内訳: 短名+sidecar 8,118 / 旧 `date_*` 28,442 / webm 等

### 未同期（将来 — blueprint §取り込みルート）

| アーカイブ | 見込み枚数 | route タグ | 備考 |
|---|---|---|---|
| **雑多なウェブ収集** | **~30,000–40,000** | `route/web` | Twitter / Google / Pinterest 等。パーサーなし |
| iCloud Photos | 未定（大） | `route/icloud` | 後回し |

**全体見込み**: 同期完了後 **~75,000–80,000 枚** 規模。

> pixiv が全体の大半なのは**現時点の同期済み分のみ**の話。web 収集追加後は比率が変わる。Phase 1 スキーマ・ingest は route 追加に耐える設計とする。

---

## 確定済み（詳細）

### OCR（ハイブリッド + ルーティング B）

| 項目 | 決定 |
|---|---|
| ingest OCR | フォルダプロファイルの `ocr_engine` |
| pixiv | `manga`（manga-ocr） |
| under.iphone | `paddle` |
| VLM | JSON `ocr_text` |
| マージ | `auto_ocr = dedicated ?? vlm ?? ""` |

### content_hash・重複（A）

`ON CONFLICT(content_hash)` → path / mtime 更新、`status=active`。embedding / OCR / VLM は再実行しない。

### サムネイル（A）

`data/thumbnails/{image_id}/thumb.webp`, `preview.webp`。原寸 < ターゲットなら拡大しない。

### CLIP（C）

Phase 1: ViT-B-32 (OpenCLIP), cuda:1。SigLIP は Phase 2。

### VLM キュー（A）

`index_jobs` + n8n（~5分）。最大 3 回リトライ。失敗 → `要再タグ`。

### ファイル消失・移動（A）

1日1回: 不在 → `missing`、同一 hash の別 path → 移動（path 更新のみ）。

### folder-rules（B）

| Phase | ルート |
|---|---|
| 1 | under.iphone + pixiv |
| 2+ | iCloud 等を追加 |

pixiv メタデータ: [folder-rules.md](../specs/folder-rules.md) §pixiv_hybrid

### 身体部位 namespace（A + 将来検討）

Phase 1 では namespace に追加しない。リスト自体は Phase 1〜2 でゆっくり設計可。

### DB テーブル（A + image_metadata）

Phase 1 で作成: `images`, `image_tags`, `image_ocr`, **`image_metadata`**, `index_jobs`, FTS5, LanceDB

`albums` は Phase 2

### FTS5（A）/ n8n（A）

FTS5 は Phase 1 から更新。n8n: 15〜30分 poll + **初回は手動バッチ**。

### 初回投入順（OQ-009 resolved — B）

**両アーカイブを Phase 1 の初回投入対象とする**（pixiv 除外しない）。

| 順序 | 対象 | 枚数 | 目的 |
|---|---|---|---|
| 1 | under.iphone | ~4,000 | パイプライン検証（embed ~2.5分） |
| 2 | pixiv | ~36,500 | 本番 bulk（embed ~25分、VLM は夜間） |

見積（Phase 0 実績 ~0.037 s/枚）:

| 処理 | 40k 枚 |
|---|---|
| embedding | ~25 分 |
| VLM | ~33 時間（キュー漸進） |

### image_metadata（OQ-010 resolved — C）

pixiv 取り込み時に `image_metadata` へ書き込み:

| フィールド | ソース |
|---|---|
| `artist`, `work_id`, `posted_at`, `source_url` | sidecar or パーサー |
| `extra_json` | `title`, `page`, `pixiv_tags`, `original_filename` 等 |

under.iphone は `image_metadata` 行なし（NULL）。

### エイリアス（OQ-007 resolved）

`config/tag_vocabulary.yaml` の `aliases`。

---

## 関連

- [open-questions.md](../open-questions.md)
- [phase-1.md](../plans/phase-1.md)
- [indexing.md](../specs/indexing.md)
- [data-model.md](../specs/data-model.md)
- [folder-rules.md](../specs/folder-rules.md)
