# UI 仕様

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §画面, §UIパーツ, §デバイス・レスポンシブ設計

## 概要

画面構成、コンポーネント、状態管理、レスポンシブ分岐の仕様。
blueprint の UI パーツ一覧を実装レベルに落とす。

## 画面

| 画面 | コンポーネント | 説明 |
|---|---|---|
| ListScreen | FilterBar + ImageGrid/Masonry/Table | 一覧画面 |
| DetailScreen | DetailPane + TagEditor + OcrEditor + SimilarPanel | 詳細画面 |

類似画像・アルバムは独立画面ではなく、詳細画面内パネル / 一覧画面内フィルタ。

## コンポーネント

| コンポーネント | 役割 | 状態 |
|---|---|---|
| FilterBar | 検索欄 + タグ/アルバムチップ | TBD |
| QueryInput | クエリ直接編集 | TBD |
| TagChip | 循環ボタン（含む/除外/解除） | TBD |
| TagPicker | タグ一覧（検索・並べ替え） | TBD |
| ImageCard | 一覧内 1 枚 | TBD |
| ImageGrid | 均一グリッド表示 | TBD |
| ImageMasonry | マゾンリー表示 | TBD |
| ImageTable | 詳細リスト表示 | TBD |
| DetailPane | 画像本体 + 前後移動 | TBD |
| TagEditor | タグ追加/削除 | TBD |
| OcrEditor | OCR 編集 | TBD |
| SimilarPanel | 類似画像タブ + 結果 | TBD |
| OriginBreadcrumb | 起点履歴パンくず | TBD |
| BulkActionBar | 複数選択時の一括操作 | TBD |

## 状態管理

### セッション状態

（TBD: Zustand store 構成）

| 状態 | 内容 |
|---|---|
| イメージリスト | 現在のフィルタ結果（順序付き image_id 集合） |
| クエリ | 現在のクエリ文字列 |
| 並び替え | ソートモード |
| 選択 | 複数選択中の image_id 集合 |
| 起点履歴 | フィルタ条件スタック（最大 5 件） |
| 詳細位置 | リスト内の現在インデックス |

### クエリ ⇔ UI 双方向同期

（TBD: TagChip 状態 ↔ クエリ文字列の変換ルール → [query-language.md](query-language.md)）

## レスポンシブ

| ブレークポイント | 想定デバイス | レイアウト |
|---|---|---|
| 狭い（〜500px） | スマホ, iPad Split View | 1 カラム、ボトムシート |
| 広い（500px〜） | PC, iPad 横向き | 2〜3 ペイン |

### 狭い画面

- フィルタ → リスト → 詳細を画面遷移
- 詳細: スワイプで前後移動
- デフォルト表示: 均一グリッド

### 広い画面

- 左: フィルタ/タグ一覧、中央: リスト、右/下: 詳細
- キーボードショートカット有効
- インライン編集

## キーボードショートカット

| キー | 動作 | 画面 |
|---|---|---|
| ← → | 前後移動 | 詳細 |
| Esc | リストに戻る | 詳細 |
| / | 検索欄フォーカス | 一覧 |
| Space | 複数選択トグル | 一覧 |
| 1〜9 | よく使うタグトグル | 一覧 |
| A | アルバムに追加 | 一覧（選択時） |
| Ctrl/Cmd+Z | 一括操作 Undo | 全体 |

（TBD: カスタムタグ割り当ての設定 UI）

## パフォーマンス要件

- 仮想スクロール必須（react-window / virtua）
- IntersectionObserver による遅延読み込み
- 詳細画面: ホイール → 前後移動、プリフェッチ
- 画像 3 段階解像度（サムネイル → プレビュー → 原寸）

## 関連ドキュメント

- [query-language.md](query-language.md) — クエリ構文
- [api.md](api.md) — データ取得 API
- [blueprint.md](../../blueprint.md) §詳細画面でのホイール高速切り替え
