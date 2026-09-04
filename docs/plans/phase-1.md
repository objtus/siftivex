# Phase 1: コアデータ層

> **状態**: Phase 1 方針確定
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
| 1.2 | LanceDB 本番セットアップ | pending | |
| 1.3 | インデックスワーカー実装 | in progress | ingest + thumb + FTS5 + OCR ルーティング + embed + VLM キュー |
| 1.4 | VLM キュー + バッチ処理 | in progress | `scripts/process_jobs.py`, `src/siftivex/jobs.py` |
| 1.5 | n8n ワークフロー構築 | pending | ingest / process_jobs を定期実行 |
| 1.6 | folder_rules.yaml 初期設定 | done | ローカル `config/folder_rules.yaml` + paths.yaml |
| 1.7 | 4万枚初回投入（embedding/OCR） | in progress | under.iphone 100 枚試走済（95 new） |
| 1.8 | VLM タグ付け漸進投入 | pending | 夜間バッチ |
| 1.9 | FastAPI プロジェクト骨格 | pending | Docker Compose 含む |

## 完了条件

- [ ] 4万枚の embedding + OCR + サムネイルが DB/LanceDB に格納
- [ ] VLM タグ付けがバックグラウンドで進行中（100% 完了は必須としない）
- [ ] 新規ファイル追加が n8n 経由で自動インデックスされる
- [ ] FastAPI コンテナが Docker Compose で起動する

## 関連ドキュメント

- [data-model.md](../specs/data-model.md)
- [indexing.md](../specs/indexing.md)
- [folder-rules.md](../specs/folder-rules.md)
- [architecture/overview.md](../architecture/overview.md)
