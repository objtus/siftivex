# Phase 1: コアデータ層

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §開発フロー

## 目的

本番 DB スキーマ確定、n8n によるフォルダ監視→自動インデックス化、4万枚の初回一括投入。

## 前提条件

- [x] Phase 0 完了（Go 判断 — 2026-09-04）
- [ ] [data-model.md](../specs/data-model.md) 確定
- [ ] [indexing.md](../specs/indexing.md) 確定
- [ ] [folder-rules.md](../specs/folder-rules.md) 確定（最低限 pixiv + legacy）
- [ ] [tags.md](../specs/tags.md) 名前空間リスト確定

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
| 1.1 | DB スキーマ migration | pending | |
| 1.2 | LanceDB 本番セットアップ | pending | |
| 1.3 | インデックスワーカー実装 | pending | embedding + OCR + サムネイル |
| 1.4 | VLM キュー + バッチ処理 | pending | |
| 1.5 | n8n ワークフロー構築 | pending | フォルダ監視 + スケジュール |
| 1.6 | folder_rules.yaml 初期設定 | pending | |
| 1.7 | 4万枚初回投入（embedding/OCR） | pending | |
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
