# インデックスパイプライン

> **状態**: 初回 bulk 投入完了（2026-09-06）
> **参照**: [blueprint.md](../../blueprint.md) §自動インデックス化フロー, [phase-1-prep.md](../decisions/phase-1-prep.md)

## 概要

新規画像の検知から DB/LanceDB への書き込みまでの処理フロー。
n8n（トリガー・スケジュール）+ FastAPI/スクリプト（処理本体）+ SQLite キュー（VLM ジョブ管理）。

## フロー

```
フォルダ監視(n8n トリガー, 15〜30分 poll)
  │
  ├─ [即時処理] scripts/n8n_task.py ingest
  │    └─ 新規 / mtime 変更ファイルのみ（差分）
  │
  ├─ [定期] scripts/n8n_task.py embed
  │
  └─ [キュー] scripts/n8n_task.py vlm
```

## 処理詳細

### content_hash

- 取り込み開始時に BLAKE3 全文を計算
- **重複時（A）**: `ON CONFLICT(content_hash)` → path / file_name / mtime 更新、`status=active`
- embedding / OCR / VLM は**再実行しない**（手動 reindex 時のみ）

### サムネイル

| 種類 | 長辺 | 形式 | 備考 |
|---|---|---|---|
| thumb | 256px | WebP q=80 | グリッド用 |
| preview | 1280px | WebP q=80 | 詳細画面用 |
| original | — | 原ファイル | ズーム時 |

原寸がターゲットより小さい場合は**拡大しない**。

### CLIP embedding

- Phase 1: **ViT-B-32 (OpenCLIP)**, cuda:1（Phase 0 継続）
- SigLIP 等への変更は Phase 2 以降（全件再 embed）
- GIF: 先頭フレームを静止画として処理

### OCR（ハイブリッド — OQ-008）

| 層 | タイミング | 内容 |
|---|---|---|
| dedicated | ingest 即時 | フォルダプロファイルの `ocr_engine` |
| VLM | キュー消化時 | JSON `ocr_text` |

**エンジンルーティング（B）** — `folder_rules.yaml` プロファイルごと:

| ocr_engine | 用途 |
|---|---|
| `manga` | pixiv 等（漫画・イラスト向け manga-ocr） |
| `paddle` | 写真・スクショ・汎用（PaddleOCR） |
| `skip` | OCR 省略（テキストほぼ無しと判断するルート） |

**マージ**: `auto_ocr = dedicated_ocr ?? vlm_ocr ?? ""`（dedicated が常に優先、VLM は補完のみ）

### VLM タグ付け

- llama.cpp port 8081（Phase 0 構成継続）
- プロンプト → [tags.md](tags.md)
- 失敗時 `要再タグ`、空結果時 `未分類`

## キュー管理（A）

`index_jobs` テーブル + n8n 定期実行（例: 5分）。

| status | 意味 |
|---|---|
| pending | 未処理 |
| running | 処理中 |
| done | 完了 |
| failed | 失敗（attempts 上限で停止、`要再タグ`） |

最大 **3** 回リトライ。

## 再インデックス

| トリガー | 対象 | 動作 |
|---|---|---|
| 手動（API） | 指定画像 | auto_tags 上書き（manual 保護） |
| `--retry-errors` | 要再タグ | VLM 再実行 |
| 定期スキャン | 監視フォルダ | 新規 / missing / 移動検出 |

## ファイル消失・移動（A）

1日1回:

1. 登録 `source_path` が存在しない → `status=missing`
2. 同一 `content_hash` が別 path で見つかる → **移動**（path 更新、タグ保持）

## 初回大量投入（OQ-009 resolved — B）

**~40,554 枚**（under.iphone 3,994 + pixiv 36,560）。同一 Phase 1 スプリント内で両方投入。

| 順 | アーカイブ | 枚数 | 備考 |
|---|---|---|---|
| 1 | under.iphone | ~4,000 | 手動バッチでパイプライン検証 |
| 2 | pixiv | ~36,500 | 検証後に bulk。VLM はキュー漸進 |

初回は n8n poll ではなく **手動バッチ1回**。以降は n8n 自動。

### 初回 bulk 実行結果（2026-09-05〜06）

| 順 | アーカイブ | ingest | embed | VLM |
|---|---|---|---|---|
| 1 | under.iphone | ✅ 3,926 | ✅ 3,924 | ✅ 3,901 caption（`run_vlm_overnight` ~15h） |
| 2 | pixiv | ✅ 36,394 | ✅ 36,381 | ⏭ Phase 2（~36k キュー pending） |

- **embed**: `make batch-archive` → `embed_pending.py --route route/pixiv`（2回目再開含む ~10h）
- **skip 15 枚**: pixiv webm 13 + under.iphone 破損 2
- **並行注意**: embed と VLM 同時実行で SQLite `database is locked` が発生した実績あり

## 関連ドキュメント

- [data-model.md](data-model.md)
- [tags.md](tags.md)
- [folder-rules.md](folder-rules.md)
- [phase-1-prep.md](../decisions/phase-1-prep.md)
