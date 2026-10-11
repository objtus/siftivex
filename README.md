# Siftivex

ローカルLLM環境を活用した画像管理・検索アプリ。自然言語検索・タグフィルタ・類似画像表示を組み合わせ、4万枚超の既存ストックから「探しやすさ」を実現する。

## ステータス

| 項目 | 状態 |
|---|---|
| フェーズ | Phase 1–2 完了 · **次: 索引 M4 / Phase 3 / タグ精度** |
| 索引 v2 | **M0〜M2 完了** · M3 おおむね完了 · M4（`inferred_ja`）未着手 |
| DB | 40,320 images / 40,305 embedded · tagger+d1 各 40,305 枚 |
| タグ方針 | **VLM `auto` 廃止済** → filename + tagger + d1 |
| UI 参照実装 | [mockup/](mockup/) v3（[設計メモ](docs/plans/mockup-design-v3.md)） |
| 自動化 | cron（ingest / embed / missing） |
| **次に読む** | [project-roadmap.md](docs/plans/project-roadmap.md) · [mockup-phase2.md](docs/plans/mockup-phase2.md) · [tag-stack-migration.md](docs/plans/tag-stack-migration.md) |

## Phase 2 開発（検索・閲覧）

```bash
make api-dev      # :8787 — FastAPI
make mockup-dev   # :5199 — 静的 UI + API プロキシ
```

ブラウザで `http://127.0.0.1:5199/`（SSH ポート転送可）。API が起動していれば **自動接続**（設定 →「API に接続する」）。

実利用チェックリスト: [docs/plans/mockup-phase2.md](docs/plans/mockup-phase2.md)  
旧 mockup（v2）: [mockup/archive/v2/](mockup/archive/v2/) または `/archive/v2/` 経由。

## ドキュメントの読み方

| レイヤー | ファイル | 役割 |
|---|---|---|
| 北極星 | [blueprint.md](blueprint.md) | 設計思想・概念モデル・方針 |
| 全体像 | [docs/architecture/overview.md](docs/architecture/overview.md) | コンポーネント構成・データフロー |
| 仕様 | [docs/specs/](docs/specs/) | 実装契約（「こう動く」の定義） |
| 計画 | [docs/plans/](docs/plans/) | フェーズ別タスク・完了条件 |
| **現在地** | [project-roadmap.md](docs/plans/project-roadmap.md) | Phase と索引 v2 |
| **UI（Phase 2）** | [ui.md](docs/specs/ui.md) · [mockup-design-v3.md](docs/plans/mockup-design-v3.md) | mockup v3 準拠 |
| 索引 v2 実行 | [tag-stack-migration.md](docs/plans/tag-stack-migration.md) | M0〜M5 |
| 判断記録 | [docs/decisions/](docs/decisions/) | ADR |
| 未決定 | [docs/open-questions.md](docs/open-questions.md) | TBD |

### 推奨する読む順番

1. [blueprint.md](blueprint.md) — 全体像と設計思想
2. [docs/plans/project-roadmap.md](docs/plans/project-roadmap.md) — いまどこにいるか
3. [docs/specs/ui.md](docs/specs/ui.md) + [mockup/](mockup/) — Phase 2 UI
4. [docs/specs/query-language.md](docs/specs/query-language.md) — 検索の核心

## 仕様（実装契約）

| ドキュメント | 内容 | 状態 |
|---|---|---|
| [data-model.md](docs/specs/data-model.md) | テーブル定義・識別子・差分レイヤー | 草案 |
| [query-language.md](docs/specs/query-language.md) | クエリ構文・FTS5/LanceDB 変換 | スケルトン（mockup と API は部分実装） |
| [api.md](docs/specs/api.md) | REST API エンドポイント | 部分実装（一覧・詳細・画像・索引） |
| [indexing.md](docs/specs/indexing.md) | 取り込み→embedding→タグパイプライン | Phase 1 + 目標フロー追記 |
| [tags.md](docs/specs/tags.md) | source 定義（tagger / d1 等） | 索引 v2 反映済 |
| [folder-rules.md](docs/specs/folder-rules.md) | 取り込みプロファイル・パーサー | スケルトン |
| [ui.md](docs/specs/ui.md) | 画面・コンポーネント・状態 | **草案（mockup v3 準拠）** |

## 実装計画

| フェーズ | 内容 | 状態 |
|---|---|---|
| [Phase 0](docs/plans/phase-0.md) | 基盤検証（数百枚で最小パイプライン） | パイプライン整備済 |
| [Phase 1](docs/plans/phase-1.md) | コアデータ層（DB・n8n・4万枚投入） | **完了** |
| [Phase 2](docs/plans/phase-2.md) | 検索・閲覧の最小 UI | **完了**（mockup v3） |
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
