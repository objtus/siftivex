# Phase 3: 編集機能

> **状態**: 着手準備（タグ編集計画確定 2026-10-12）  
> **参照**: [blueprint.md](../../blueprint.md) §タグ・OCRの手動修正 · [phase-2.md](phase-2.md)

## 目的

タグ・OCR の手動修正、アルバム、一括操作を実装する。

## 前提条件

- [x] Phase 2 完了（mockup v3 · 2026-10-12）
- [x] タグ差分レイヤー方針（blueprint + [tags.md](../specs/tags.md)）
- [~] [tag-editing.md](../specs/tag-editing.md) — v1 草案 · 実装は [tag-editing-implementation.md](tag-editing-implementation.md)
- [ ] [api.md](../specs/api.md) 編集系エンドポイント確定（PATCH tags 本文は tag-editing 仕様に追随）

## スコープ

### In

- タグ手動追加/削除（差分レイヤー）— **v1 詳細 1 枚**
- OCR 手動上書き
- アルバム CRUD + メンバー管理
- 複数選択 + 一括操作（タグ付与/削除、アルバム追加、アーカイブ、再タグ付け）
- Undo（Ctrl/Cmd+Z）

### Out

- 類似画像表示（Phase 2 拡張候補）
- 逆引き検索
- タグ一括リネーム（運用ツール化は後）

## タスク

| # | タスク | 状態 | 備考 |
|---|---|---|---|
| **3.1** | タグ編集 API + TagEditor | **計画済** | [tag-editing-implementation.md](tag-editing-implementation.md) T1–T2 |
| 3.2 | OCR 編集 API + OcrEditor | pending | |
| 3.3 | アルバム API + UI | pending | |
| 3.4 | 複数選択 + BulkActionBar | pending | タグ一括は T4 |
| 3.5 | 一括操作 API | pending | |
| 3.6 | Undo 機能 | pending | タグ PATCH 逆操作 |
| 3.7 | 未分類レビューフロー検証 | pending | `tag:未分類` フィルタ |

## 完了条件（Phase 3 全体）

- [ ] 詳細画面でタグ追加/削除ができ、tagger/d1 再実行後も手動修正が保持される
- [ ] アルバム作成 → 画像追加 → フィルタで表示、の一連が動く
- [ ] 複数選択 → 一括タグ付与 → Undo、が動く
- [ ] 未分類画像のレビュー（フィルタ → 詳細 → 修正 → 次へ）が実用的

### v1 タグ編集のみ（3.1 部分完了）

- [ ] PATCH tags · mockup 編集モード · テスト 5 件（仕様 §テスト観点）

## 関連ドキュメント

- [decisions/tag-editing.md](../decisions/tag-editing.md)
- [specs/tag-editing.md](../specs/tag-editing.md)
- [tags.md](../specs/tags.md)
- [data-model.md](../specs/data-model.md)
- [api.md](../specs/api.md)
- [ui.md](../specs/ui.md)
