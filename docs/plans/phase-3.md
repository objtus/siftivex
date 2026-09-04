# Phase 3: 編集機能

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §開発フロー

## 目的

タグ・OCR の手動修正、アルバム、一括操作を実装する。

## 前提条件

- [ ] Phase 2 完了
- [ ] [tags.md](../specs/tags.md) 差分レイヤー仕様確定
- [ ] [api.md](../specs/api.md) 編集系エンドポイント確定

## スコープ

### In

- タグ手動追加/削除（差分レイヤー）
- OCR 手動上書き
- アルバム CRUD + メンバー管理
- 複数選択 + 一括操作（タグ付与/削除、アルバム追加、アーカイブ、再タグ付け）
- Undo（Ctrl/Cmd+Z）

### Out

- 類似画像表示
- 起点履歴
- 逆引き検索
- レスポンシブ広い画面レイアウト

## タスク

| # | タスク | 状態 | 備考 |
|---|---|---|---|
| 3.1 | タグ編集 API + TagEditor | pending | 差分レイヤー |
| 3.2 | OCR 編集 API + OcrEditor | pending | |
| 3.3 | アルバム API + UI | pending | |
| 3.4 | 複数選択 + BulkActionBar | pending | |
| 3.5 | 一括操作 API | pending | |
| 3.6 | Undo 機能 | pending | |
| 3.7 | 未分類レビューフロー検証 | pending | `tag:未分類` フィルタ |

## 完了条件

- [ ] 詳細画面でタグ追加/削除ができ、VLM 再実行後も手動修正が保持される
- [ ] アルバム作成 → 画像追加 → フィルタで表示、の一連が動く
- [ ] 複数選択 → 一括タグ付与 → Undo、が動く
- [ ] 未分類画像のレビュー（フィルタ → 詳細 → 修正 → 次へ）が実用的

## 関連ドキュメント

- [tags.md](../specs/tags.md)
- [data-model.md](../specs/data-model.md)
- [api.md](../specs/api.md)
- [ui.md](../specs/ui.md)
