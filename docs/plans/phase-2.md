# Phase 2: 検索・閲覧の最小 UI

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §開発フロー

## 目的

フィルタ（タグ/自然言語）→ グリッド → 詳細の統一モデルを動かし、「実用に耐えるか」を検証する。

## 前提条件

- [ ] Phase 1 完了
- [ ] [query-language.md](../specs/query-language.md) 確定
- [ ] [api.md](../specs/api.md) 検索・一覧エンドポイント確定
- [ ] [ui.md](../specs/ui.md) ListScreen / DetailScreen 確定

## スコープ

### In

- React + Vite プロジェクト
- 検索 API（タグ + 自然言語 + OCR）
- 一覧画面（均一グリッド、仮想スクロール）
- 詳細画面（画像表示 + 前後移動）
- FilterBar + QueryInput + TagChip

### Out

- マゾンリー / 詳細リスト表示
- タグ/OCR 編集
- アルバム
- 類似画像
- レスポンシブ（広い画面レイアウト）

## タスク

| # | タスク | 状態 | 備考 |
|---|---|---|---|
| 2.1 | React + Vite プロジェクト作成 | pending | |
| 2.2 | 検索 API 実装 | pending | FTS5 + LanceDB |
| 2.3 | 画像配信 API（サムネイル + プレビュー） | pending | |
| 2.4 | FilterBar + QueryInput | pending | |
| 2.5 | ImageGrid + 仮想スクロール | pending | |
| 2.6 | DetailScreen + 前後移動 | pending | |
| 2.7 | 実利用検証 + フィードバック記録 | pending | |

## 完了条件

- [ ] タグフィルタで数百〜数千枚をサクサク絞り込める
- [ ] 自然言語検索で意味的に関連する画像が返る
- [ ] 詳細画面で前後移動がスムーズ（プレビューサイズ）
- [ ] 実際に資料探しに使ってみて「使える/使えない」の判断ができる

## 関連ドキュメント

- [query-language.md](../specs/query-language.md)
- [api.md](../specs/api.md)
- [ui.md](../specs/ui.md)
