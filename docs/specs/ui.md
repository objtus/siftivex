# UI 仕様

> **状態**: 草案（**mockup v3 準拠** · 2026-10-12）  
> **思想**: [ui-philosophy.md](../decisions/ui-philosophy.md) — 資料探し・リスト中心  
> **参照実装**: [mockup/](../../mockup/) · [mockup-design-v3.md](../plans/mockup-design-v3.md)  
> **API**: [api.md](api.md) · **クエリ**: [query-language.md](query-language.md)

## 概要

Phase 2 の UI は **探索（一覧）** と **閲覧（詳細）** の二モード。フィルタは左サイドバー常設（狭い画面ではドロワー）。  
PC レイアウトは **案 B**（探索 ⇔ 閲覧の全画面切替）を採用（OQ-UI-01 解決 · 2026-10-12）。

React 本番 UI は本仕様と mockup v3 を写す。Phase 3 以降の編集系コンポーネントは末尾に「将来」として記載。

## アプリモード

| モード | CSS | 表示 |
|---|---|---|
| `explore` | `.app.mode-explore` | topbar + sidebar + list-pane |
| `view` | `.app.mode-view` | topbar + viewer（list/sidebar 非表示） |

- 詳細を開くと `view` · `history.pushState` で URL 履歴に積む
- 戻る: 「一覧へ」· Esc · ブラウザ戻る · `popstate`

## 画面構成（PC · explore）

```
topbar:     ブランド · 検索 · 設定
sidebar:    ルート · 絞り込み中 · 結果内タグファセット
list-pane:  件数/履歴 · 並び · レイアウト · サムネサイズ · グリッド/表
```

## 画面構成（PC · view）

```
viewer-bar: 一覧へ · 作品送り ‹ n / N › · （狭い幅）情報トグル
viewer-stage: 画像 · 左右 edge-nav
info-panel:   作品コンテキスト · page strip · タグ（source 別）· メタ dl
```

## コンポーネント（Phase 2 · mockup v3）

| コンポーネント | DOM / ID | 役割 | 状態 |
|---|---|---|---|
| Topbar | `#query-input`, `#btn-settings`, `#btn-filters` | 検索 · 設定 · （compact）フィルタ | ✅ mockup |
| FilterPane | `#filter-pane`, `#route-list` | ルート · ファセット | ✅ |
| ActiveFilters | `#chip-row`, `#btn-clear-filters` | 含む/除外チップ | ✅ |
| TagFacets | `#tag-list`, `#tag-filter` | 結果内集計 · 行クリックで絞り込み | ✅ |
| ListToolbar | `#sort-select`, `#layout-seg`, `#thumb-size` | 並び · 4 レイアウト · 密度 | ✅ |
| ImageGrid | `#image-grid`, `.image-card` | サムネのみ（メタ非表示） | ✅ |
| ImageTable | `#table-wrap`, `#table-body` | ファイル名/ルート/寸法/タグ/スコア | ✅ |
| Viewer | `#detail-pane`, `#detail-image` | プレビュー · ホイール送り | ✅ |
| WorkNav | `#page-strip`, `#work-prev/next` | 作品内ページ（データがあるとき） | ✅ |
| DetailTags | `#detail-tags` | `tag_sources` をレイヤ表示 | ✅ |
| Settings | `#settings`, `#set-api`, `#theme-seg` | API · 索引 · テーマ | ✅ |
| OriginBreadcrumb | `#breadcrumb` | 起点履歴（2 件以上で表示） | ✅ |

### Phase 3 — TagEditor（計画 · [tag-editing.md](tag-editing.md)）

| コンポーネント | 役割 | 状態 |
|---|---|---|
| TagEditor | 詳細 `#detail-tags` · 編集トグル · 追加/非表示/復元 · PATCH | 未実装 |
| OcrEditor | OCR 編集 | 未実装 |
| BulkActionBar | 一括操作 | 未実装 |
| SimilarPanel | 類似画像（CLIP 還流） | 未実装 |
| VlmCaptionPanel | オンデマンドキャプション | 未実装 |

**TagEditor v1**: API 接続時のみ。「タグを編集」ON でチップ × = 非表示 · 入力 = 追加 · `manual_removed` を折りたたみ表示。編集中はタグクリックによる **検索フィルタは無効**（誤操作防止）。閲覧時は Phase 2 どおり bridge label クリック → クエリ。

### Phase 3 その他（未実装）

（OcrEditor · BulkActionBar 等 — 上表参照）

## レイアウト（一覧グリッド）

| `gridLayout` | 説明 |
|---|---|
| `justified` | 行高固定・幅は aspect で伸縮 |
| `masonry` | 最短列へ配置 |
| `square` | CSS 正方形タイル |
| `table` | 行リスト（タグプレビュー列あり） |

`thumbSize` 80–280px · localStorage `siftivex.mockup.prefs`。

## 状態管理（mockup · セッション）

| 状態 | 内容 |
|---|---|
| `appMode` | `explore` \| `view` |
| `query` | 検索文字列（`tag:` / `-tag:` / 自然言語） |
| `route` | ルートフィルタ |
| `tagStates` | タグ → 0 なし / 1 含む / 2 除外 |
| `originStack` | 起点履歴（クエリ+ルート+scrollTop） |
| `activeId` / `detailIndex` | 閲覧中 image_id とリスト内位置 |
| `apiImages` + `offset` | API ページング（200 件/step） |
| `gridLayout`, `thumbSize`, `sort`, `theme` | 永続 prefs |

本番 React では同等 store（Zustand 等）を想定。URL 同期（クエリパラメータ）は Phase 2 完了条件の拡張候補。

## クエリ ⇔ UI

- **正本**: 検索欄のクエリ文字列 → API は `GET /api/images?q=…` にそのまま渡す（同じ文字列なら同じ結果）。
- 検索欄: `tag:名前`（Tag Bridge ラベル可）· `tag:=名前`（厳密・bridge 無視）· `-tag:名前` · 残りは CLIP テキスト
- **Tag Bridge**: 詳細 / ファセットで bridge **member** をクリック → クエリには **`tag:<代表label>`** を載せる（`school uniform` 単体は載せない）。絞り込み中は member チップも label 条件でハイライト。
- クリック: 含む · Shift+クリック: 除外 · チップ × / 「すべて解除」
- debounce 後に API 再取得 · Enter で即時

詳細: [query-language.md](query-language.md) · [tag-bridge.md](tag-bridge.md)

## レスポンシブ

| 幅 | 挙動 |
|---|---|
| >1099px | サイドバー常設 |
| ≤1099px | サイドバー = 左ドロワー（`#btn-filters`）· scrim |
| ≤899px | 閲覧: 画像上 + 情報下 · `info-hidden` で画像全面 |
| ≤599px | ブランド非表示 · 表の列省略 |

`viewport-fit=cover` · safe-area padding on `#app`。

## キーボード（Phase 2 実装分）

| キー | 動作 | 条件 |
|---|---|---|
| `/` | 検索欄フォーカス | explore |
| `←` `→` | 前後の画像 | view |
| `[` `]` | 作品内ページ | view · 複数ページ時 |
| `Esc` | オーバーレイ閉じ · 一覧へ | 優先順: overlay → view |
| ホイール | 前後の画像 | view · `#detail-image` 上 |

Phase 3 予定（仕様のみ）: Space 複数選択 · 一括操作ショートカット等。

## タグ表示（source）

[tags.md](tags.md) に従い **マージせず** ブロック表示:

- 構造化（`auto_d1`）
- ファイル名 / pixiv（`filename`）
- Tagger（`auto_tagger`）
- 推定 JA / VLM 旧 / 手動（データがあるとき）

色点: d1=青 · filename=緑 · tagger=中性（[mockup-design-v3.md](../plans/mockup-design-v3.md)）。

## パフォーマンス

- 一覧: IntersectionObserver + サムネ **同時 6 本** · リトライ
- 詳細: プレビュー img をプリロードして DOM 挿入（二重 fetch 回避）
- 4 万枚: **全件クライアント保持しない** · API offset ページング（仮想スクロールは本番 UI 課題）

## テーマ

`data-theme`: `auto` \| `dark` \| `light` · `color-scheme` 同期。

## 関連ドキュメント

- [ui-philosophy.md](../decisions/ui-philosophy.md)
- [mockup-phase2.md](../plans/mockup-phase2.md) — 検証チェックリスト
- [phase-2.md](../plans/phase-2.md)
