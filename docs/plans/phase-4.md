# Phase 4: 仕上げ・拡張

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §開発フロー

## 目的

類似画像、レスポンシブ、パフォーマンスチューニング、低優先度機能を追加する。

## 前提条件

- [ ] Phase 3 完了
- [ ] Phase 2/3 の実利用フィードバック反映済み

## スコープ

### In

- 類似画像表示（色味/時期/モチーフ）
- 起点履歴（昇格・復帰・パンくず）
- レスポンシブ対応（狭い/広い画面）
- マゾンリー / 詳細リスト表示モード
- キーボードショートカット完全版
- パフォーマンスチューニング
- カラーパレット抽出
- 逆引き画像検索（SauceNAO）
- 重複画像検出（pHash）

### Out

- 動的アルバム（設計上見送り済み）
- 配信セーフモード（設計上見送り済み）

## タスク

| # | タスク | 状態 | 優先度 | 備考 |
|---|---|---|---|---|
| 4.1 | SimilarPanel（色味軸） | pending | 高 | CLIP embedding |
| 4.2 | SimilarPanel（時期軸） | pending | 中 | Exif/ファイル日付 |
| 4.3 | SimilarPanel（モチーフ軸） | pending | 低 | タグ重なりで代用? |
| 4.4 | 起点履歴 + OriginBreadcrumb | pending | 高 | |
| 4.5 | レスポンシブ（狭い画面） | pending | 高 | ボトムシート等 |
| 4.6 | レスポンシブ（広い画面） | pending | 中 | 2〜3 ペイン |
| 4.7 | ImageMasonry | pending | 低 | PC 限定 |
| 4.8 | ImageTable | pending | 中 | カラムソート |
| 4.9 | パフォーマンスチューニング | pending | 高 | クエリ最適化等 |
| 4.10 | カラーパレット抽出 | pending | 低 | k-means |
| 4.11 | 逆引き検索（SauceNAO） | pending | 中 | オンデマンド |
| 4.12 | 重複検出（pHash） | pending | 低 | |

## 完了条件

- [ ] 日常の資料探しが Siftivex だけで完結する
- [ ] iPad Split View で快適に閲覧できる
- [ ] 4万枚規模で検索・一覧が体感 1 秒以内

## 関連ドキュメント

- [query-language.md](../specs/query-language.md) — `similar_to:` トークン
- [ui.md](../specs/ui.md) — レスポンシブ・SimilarPanel
- [api.md](../specs/api.md) — 類似画像・逆引き API
- [blueprint.md](../../blueprint.md) §逆引き画像検索
