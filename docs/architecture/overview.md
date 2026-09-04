# システム全体像

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §推奨技術スタック

## 概要

Siftivex は既存の objtus-server 環境（Docker, llama-swap, n8n, Tailscale）上で動作する、1ユーザー向けローカル画像アーカイブ検索アプリ。

## コンポーネント構成

```
[TBD: コンポーネント図]

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  React UI   │────▶│  FastAPI    │────▶│  SQLite     │
│  (Vite)     │     │  (Python)   │     │  + FTS5     │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │  LanceDB    │
                    │  (embedded) │
                    └─────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  n8n        │────▶│  インデックス │────▶│  llama-swap │
│  (監視/キュー)│     │  ワーカー    │     │  (VLM)      │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │  CLIP/OCR   │
                    │  (別 GPU)   │
                    └─────────────┘
```

## データフロー

### 取り込み

```
フォルダ監視(n8n)
  → 新規ファイル検知
  → [即時] CLIP embedding + OCR → DB/LanceDB 書き込み
  → [キュー] VLM タグ付け → auto_tags 更新
```

→ 詳細: [indexing.md](../specs/indexing.md)

### 検索・閲覧

```
UI クエリ入力
  → FastAPI（クエリパース）
  → SQLite FTS5（タグ/OCR）+ LanceDB ANN（意味検索）
  → 結果マージ → イメージリスト返却
  → UI 表示（仮想スクロール）
```

→ 詳細: [query-language.md](../specs/query-language.md), [api.md](../specs/api.md)

## デプロイ構成

| 項目 | 方針 |
|---|---|
| コンテナ | Docker Compose（既存 compose 群に追加） |
| 公開範囲 | Tailscale ネットワーク内限定 |
| 認証 | Basic 認証（アプリレベル） |
| ファイル同期 | Syncthing（元画像フォルダ） |

## 関連ドキュメント

- [data-model.md](../specs/data-model.md) — 永続化層
- [indexing.md](../specs/indexing.md) — バッチ処理
- [blueprint.md](../../blueprint.md) §セキュリティ — セキュリティ方針
