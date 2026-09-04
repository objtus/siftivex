# Siftivex

ローカルLLM環境を活用した画像管理・検索アプリ。自然言語検索・タグフィルタ・類似画像表示を組み合わせ、4万枚超の既存ストックから「探しやすさ」を実現する。

## ステータス

| 項目 | 状態 |
|---|---|
| フェーズ | 設計 + Phase 0 パイプライン（embedding まで） |
| コード | Phase 0 進行中 |
| 画像同期 | under.iphone 同期済（3,994枚） |
| 最終更新 | 2026-09-04 |

## ドキュメントの読み方

| レイヤー | ファイル | 役割 |
|---|---|---|
| 北極星 | [blueprint.md](blueprint.md) | 設計思想・概念モデル・方針 |
| 全体像 | [docs/architecture/overview.md](docs/architecture/overview.md) | コンポーネント構成・データフロー |
| 仕様 | [docs/specs/](docs/specs/) | 実装契約（「こう動く」の定義） |
| 計画 | [docs/plans/](docs/plans/) | フェーズ別タスク・完了条件 |
| 判断記録 | [docs/decisions/](docs/decisions/) | ADR（設計判断の記録） |
| 未決定 | [docs/open-questions.md](docs/open-questions.md) | TBD 事項のトラッキング |

### 推奨する読む順番

1. [blueprint.md](blueprint.md) — 全体像と設計思想
2. [docs/architecture/overview.md](docs/architecture/overview.md) — システム構成
3. [docs/specs/data-model.md](docs/specs/data-model.md) — データの土台
4. [docs/specs/query-language.md](docs/specs/query-language.md) — 検索の核心
5. [docs/plans/phase-0.md](docs/plans/phase-0.md) — 最初の実装計画

## 仕様（実装契約）

| ドキュメント | 内容 | 状態 |
|---|---|---|
| [data-model.md](docs/specs/data-model.md) | テーブル定義・識別子・差分レイヤー | 草案 |
| [query-language.md](docs/specs/query-language.md) | クエリ構文・FTS5/LanceDB 変換 | スケルトン |
| [api.md](docs/specs/api.md) | REST API エンドポイント | スケルトン |
| [indexing.md](docs/specs/indexing.md) | 取り込み→embedding→OCR→VLM パイプライン | スケルトン |
| [tags.md](docs/specs/tags.md) | 名前空間リスト・VLM プロンプト | スケルトン |
| [folder-rules.md](docs/specs/folder-rules.md) | 取り込みプロファイル・パーサー | スケルトン |
| [ui.md](docs/specs/ui.md) | 画面・コンポーネント・状態遷移 | スケルトン |

## 実装計画

| フェーズ | 内容 | 状態 |
|---|---|---|
| [Phase 0](docs/plans/phase-0.md) | 基盤検証（数百枚で最小パイプライン） | パイプライン整備済 |
| [Phase 1](docs/plans/phase-1.md) | コアデータ層（DB・n8n・4万枚投入） | スケルトン |
| [Phase 2](docs/plans/phase-2.md) | 検索・閲覧の最小 UI | スケルトン |
| [Phase 3](docs/plans/phase-3.md) | 編集機能（タグ/OCR/アルバム/一括操作） | スケルトン |
| [Phase 4](docs/plans/phase-4.md) | 仕上げ・拡張 | スケルトン |

## 開発（Phase 0 パイプライン）

```bash
cp config/phase0.yaml.example config/phase0.yaml   # パスを編集
make install
make list-tasks
make pipeline
```

詳細: [docs/plans/phase-0-pipeline.md](docs/plans/phase-0-pipeline.md)

## 画像同期（Windows ↔ サーバー）

```bash
# 1. Syncthing で under.iphone を同期（手順書参照）
# 2. 同期確認後
make task-0.1 && make task-0.2b && make pipeline
```

手順: [docs/setup/windows-sync.md](docs/setup/windows-sync.md)

## その他

- [未決定事項](docs/open-questions.md)
- [設計判断の記録（ADR）](docs/decisions/)
