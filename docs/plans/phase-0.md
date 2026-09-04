# Phase 0: 基盤検証

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §開発フロー

## 目的

数百枚程度のサブセットで最小パイプラインを通し、4万枚に広げる前に処理時間・精度の肌感を掴む。

## 前提条件

- [x] [OQ-005](../open-questions.md): `image_id` 生成規則が決定
- [x] [OQ-006](../open-questions.md): 検証用データセット方針が決定（manifest 生成はタスク 0.1）
- [x] [data-model.md](../specs/data-model.md): 最小スキーマ草案

## スコープ

### In

- CLIP embedding 生成 → LanceDB 検索
- VLM タグ付け → SQLite 保存
- 最小 CLI or スクリプトでの動作確認
- 処理時間・精度の記録

### Out

- Web UI
- n8n 連携
- フォルダ監視
- 本番 DB スキーマの完全版

## タスク

| # | タスク | 状態 | 備考 |
|---|---|---|---|
| 0.1 | 検証用データセット選定（300枚） | ready | `make task-0.1` |
| 0.2 | 最小 DB スキーマ作成 | ready | `make task-0.2` |
| 0.2b | manifest → DB 投入 | ready | `make task-0.2b` |
| 0.3 | CLIP embedding スクリプト | stub | `scripts/embed.py` |
| 0.4 | LanceDB 書き込み + 検索テスト | stub | `scripts/search_test.py` |
| 0.5 | VLM タグ付けスクリプト | stub | `scripts/vlm_tag.py` |
| 0.6 | 処理時間計測・記録 | pending | |
| 0.7 | タグ精度の目視評価 | pending | サンプル 20〜30 枚 |

→ パイプライン実行方法: [phase-0-pipeline.md](phase-0-pipeline.md)

## 完了条件

- [ ] 数百枚の embedding が LanceDB に格納され、自然言語クエリで意味検索が動く
- [ ] 同サブセットの VLM タグ付けが SQLite に保存され、内容を目視確認できる
- [ ] 1枚あたりの処理時間が記録され、4万枚 extrapolation が算出できる
- [ ] Phase 1 への Go/No-Go 判断ができる

## 成果物

| 成果物 | 置き場所 |
|---|---|
| 検証用 manifest | [data/phase0/manifest.json](../../data/phase0/manifest.json) |
| 検証結果レポート | `data/phase0/results/` |
| SQLite DB | `data/siftivex.db` |
| LanceDB | `data/lance/` |

## リスク

| リスク | 影響 | 対策 |
|---|---|---|
| VLM タグ精度が期待以下 | 名前空間設計の見直し | Phase 0 で早期発見が目的 |
| embedding 検索が遅い | LanceDB 設定見直し | インデックスパラメータ調整 |
| GPU メモリ不足 | CLIP/VLM 同時実行不可 | プロセス分離（設計通り） |

## 関連ドキュメント

- [data-model.md](../specs/data-model.md)
- [indexing.md](../specs/indexing.md)
- [tags.md](../specs/tags.md)
