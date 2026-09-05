# Phase 1: コアデータ層

> **状態**: **クローズ**（2026-09-06 監査済み）
> **参照**: [blueprint.md](../../blueprint.md) §開発フロー

## 目的

本番 DB スキーマ確定、n8n によるフォルダ監視→自動インデックス化、4万枚の初回一括投入。

## 前提条件

- [x] Phase 0 完了（Go 判断 — 2026-09-04）
- [x] [indexing.md](../specs/indexing.md) 方針確定 → [phase-1-prep.md](../decisions/phase-1-prep.md)
- [x] [data-model.md](../specs/data-model.md) 確定（OQ-010 — C, 2026-09-04）
- [x] [folder-rules.md](../specs/folder-rules.md) pixiv パーサー（OQ-002 — 2026-09-04）
- [x] [tags.md](../specs/tags.md) namespace（身体部位/ は Phase 1 見送り）

**Phase 1 決定セット確定**（2026-09-04）→ [phase-1-prep.md](../decisions/phase-1-prep.md)

pixiv 同期完了: **36,560** + under.iphone **3,994** = **~40,554 枚**

## スコープ

### In

- DB スキーマ確定（images, tags, albums, embeddings, キュー）
- n8n フォルダ監視 → インデックスパイプライン
- 4万枚初回投入（embedding/OCR 先行、VLM は漸進）
- FastAPI 骨格（エンドポイント未実装でも可）

### Out

- Web UI
- 検索 API の完全実装
- 手動編集機能

## タスク

| # | タスク | 状態 | 備考 |
|---|---|---|---|
| 1.1 | DB スキーマ migration | done | `schema/phase1_migration.sql`, `scripts/migrate_db.py` |
| 1.2 | LanceDB 本番セットアップ | done | bulk load 完了（~40,505 行）。HNSW チューニングは Phase 2 可 |
| 1.3 | インデックスワーカー実装 | done | ingest + thumb + FTS5 + OCR ルーティング + embed + VLM キュー |
| 1.4 | VLM キュー + バッチ処理 | done | `scripts/process_jobs.py`, `run_vlm_overnight.py` |
| 1.5 | 定期自動化（n8n / cron） | done | **本番: cron**（2026-09-06）。`n8n/workflows/` は将来用 |
| 1.6 | folder_rules.yaml 初期設定 | done | ローカル `config/folder_rules.yaml` + paths.yaml |
| 1.7 | 4万枚初回投入（embedding/OCR） | done | 2026-09-06 完了（下表） |
| 1.8 | VLM タグ付け漸進投入 | done* | under.iphone 99%。pixiv → Phase 2（意図的スコープ外） |
| 1.9 | FastAPI プロジェクト骨格 | done | `/health`, 画像配信, `/api/index/status`。Compose 骨格あり |

## 初回 bulk 投入 実績（2026-09-05〜06）

| ルート | ingest | embed | VLM caption | 備考 |
|---|---|---|---|---|
| under.iphone | 3,926 | 3,924 | 3,901 | embed 未了 2（破損）、VLM 未了 ~25（JSON 失敗・再試行可） |
| pixiv | 36,394 | 36,381 | — | embed 未了 13（webm 等）。VLM **Phase 2**（~36k pending） |
| **合計** | **40,320** | **40,305** | — | ハッシュ重複 166（pixiv）。LanceDB ~40,505 行 |

**embed 所要**: pixiv ~17.5k 枚の再開分含め **約10時間**（~3,300枚/時）。VLM overnight（under.iphone）**~15時間**。

**運用上の注意**: embed と VLM を同時実行すると SQLite ロック競合あり。別プロセスで回す。

## クローズ監査（2026-09-06）

| 完了条件 | 結果 |
|---|---|
| ~4万枚 ingest + embed + サムネ | ✅ 40,320 active / 40,305 embedded / ~40k thumbs |
| LanceDB | ✅ 40,505 行 |
| FTS5 `image_search` | ✅ 40,021 行 |
| pixiv `image_metadata` | ✅ 36,378 行 |
| under.iphone VLM | ✅ 3,902 / 3,926 caption（99.4%） |
| 定期自動化 | ✅ cron 3 本（ingest 20分 / embed 毎時 / missing 日次）。VLM は [vlm-on-demand.md](../decisions/vlm-on-demand.md) |
| FastAPI 骨格 | ✅ 実装済（常駐は任意、`make api-dev`） |
| pytest | ✅ 37 passed |

### 既知の残件（Phase 1 ブロッカーではない）

| 項目 | 数 | 対応 |
|---|---|---|
| embed skip | 15 | webm 9 + 読取不可 jpeg/png 6 — CLIP 非対応 |
| under.iphone VLM 未了 | ~24 | Phase 2 UI 手動 or CLI |
| pixiv VLM | ~36k pending | Phase 2 オンデマンド（[vlm-on-demand.md](../decisions/vlm-on-demand.md)） |
| n8n UI | 未デプロイ | cron で代替済。JSON は `n8n/workflows/` |
| API 常駐 | 停止中 | 必要時 `make api-dev` または Compose |

## 完了条件

- [x] 4万枚の embedding + サムネイルが DB/LanceDB に格納（未読 15 枚は skip）
- [x] under.iphone VLM タグ付け（pixiv VLM は Phase 2 — スコープ外）
- [x] 新規ファイル追加が cron 経由で自動インデックス（`scripts/n8n_task.py`）
- [x] FastAPI 骨格 + `/health` 動作確認済み

## Phase 2 へ

- 検索 API 本実装 + React UI → [phase-2.md](phase-2.md)
- pixiv VLM 漸進投入（~36k キュー pending）

## 関連ドキュメント

- [data-model.md](../specs/data-model.md)
- [indexing.md](../specs/indexing.md)
- [folder-rules.md](../specs/folder-rules.md)
- [architecture/overview.md](../architecture/overview.md)
