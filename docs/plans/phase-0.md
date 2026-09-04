# Phase 0: 基盤検証

> **状態**: 完了（Go: Phase 1 へ）
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
| 0.1 | 検証用データセット選定 | done | under.iphone 300枚（全3994枚中） |
| 0.2 | 最小 DB スキーマ作成 | done | |
| 0.2b | manifest → DB 投入 | done | 299 images |
| 0.3 | CLIP embedding スクリプト | done | 298枚成功、1枚スキップ |
| 0.4 | LanceDB 書き込み + 検索テスト | done | under.iphone で動作確認済 |
| 0.5 | VLM タグ付けスクリプト | done | 293/299枚（Qwen3.6 35B, ~3.0s/img, 6 errors） |
| 0.6 | 処理時間計測・記録 | done | embed + vlm timing JSON |
| 0.7 | タグ精度の目視評価 | done | `make review` → 25枚サンプル HTML（2026-09-04） |

→ パイプライン実行方法: [phase-0-pipeline.md](phase-0-pipeline.md)

## 完了条件

- [x] 数百枚の embedding が LanceDB に格納され、自然言語クエリで意味検索が動く（298枚、`search_test.py` 確認済）
- [x] 同サブセットの VLM タグ付けが SQLite に保存され、内容を目視確認できる（298枚 auto タグ、`review/index.html`）
- [x] 1枚あたりの処理時間が記録され、4万枚 extrapolation が算出できる（下表）
- [x] Phase 1 への Go/No-Go 判断ができる（**Go**）

## 処理時間 extrapolation（4万枚）

| 工程 | 実測（Phase 0） | 4万枚見積 | 備考 |
|---|---|---|---|
| CLIP embed | 0.037 s/枚（298枚） | **~25 分** | ViT-B-32, cuda:1 |
| VLM タグ | 2.96 s/枚（293枚） | **~33 時間** | Qwen3.6 35B, cuda:0 |
| 合計（直列） | — | **~34 時間** | 1枚破損・JSON エラー数枚は再実行で回収可 |

→ 詳細: `data/phase0/results/embed_timing.json`, `vlm_timing.json`

## Go/No-Go（2026-09-04）

| 観点 | 結果 | メモ |
|---|---|---|
| パイプライン | Go | manifest → DB → embed → VLM → review まで通過 |
| 意味検索 | Go | LanceDB ANN 動作確認済 |
| VLM タグ品質 | Go（条件付き） | 語彙・tag_notes 調整後は目視で許容範囲。JSON パース失敗は ~2%（リトライで大半回復） |
| 処理時間 | Go | 4万枚 VLM が overnight バッチ想定内 |
| 既知問題 | 記録 | IMG5058.JPG 破損、VLM JSON エラー 6件/299 |

**判断: Phase 1 へ進む。** 本番投入前に route 別語彙・`身体部位/` namespace は Phase 1 で検討。

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
