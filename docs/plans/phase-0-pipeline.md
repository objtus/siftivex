# Phase 0 パイプライン

> **参照**: [phase-0.md](phase-0.md), [data-model.md](../specs/data-model.md)

## 概要

Phase 0 の検証タスクを順番に実行する CLI パイプライン。

```
0.1 select_sample   → manifest 生成
0.2 init_db         → SQLite スキーマ
0.2b import_manifest → manifest → images
0.3 embed           → CLIP → LanceDB  (stub)
0.4 search_test     → ANN 検索       (stub)
0.5 vlm_tag         → VLM → tags     (stub)
```

## セットアップ

```bash
# 1. 設定ファイル
cp config/phase0.yaml.example config/phase0.yaml
# config/phase0.yaml の source パスを編集

# 2. Python 環境
make install          # 基本依存
make install-embed    # embedding 用（0.3 以降）

# GPU: CLIP は cuda:1 をデフォルト（cuda:0 は VLM 用）
# 変更: SIFTIVEX_DEVICE=cuda:0 make pipeline
```

## 実行

```bash
# タスク一覧
make list-tasks

# 全タスク実行
make pipeline

# 個別タスク
make task-0.1
make task-0.2
make task-0.2b
```

または:

```bash
.venv/bin/python -m siftivex.pipeline 0.1 0.2 0.2b
```

## ディレクトリ

| パス | 内容 |
|---|---|
| `src/siftivex/` | 共通ライブラリ（ids, db, config, pipeline） |
| `scripts/` | タスク別スクリプト |
| `schema/phase0.sql` | Phase 0 DB スキーマ |
| `config/phase0.yaml` | 検証データセット設定（gitignore） |
| `data/phase0/manifest.json` | 生成された manifest（gitignore） |

## タスク状態

| # | スクリプト | 状態 |
|---|---|---|
| 0.1 | `scripts/select_phase0_sample.py` | 実装済 |
| 0.2 | `scripts/init_db.py` | 実装済 |
| 0.2b | `scripts/import_manifest.py` | 実装済 |
| 0.3 | `scripts/embed.py` | 実装済 |
| 0.4 | `scripts/search_test.py` | 実装済 |
| 0.5 | `scripts/vlm_tag.py` | stub |
