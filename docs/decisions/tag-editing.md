# タグ手動編集 — 差分レイヤーと UI 方針

- **日付**: 2026-10-12
- **状態**: accepted（実装前）
- **仕様**: [tag-editing.md](../specs/tag-editing.md) · **計画**: [tag-editing-implementation.md](../plans/tag-editing-implementation.md)
- **参照**: [blueprint.md](../../blueprint.md) §タグ・OCRの手動修正 · [tags.md](../specs/tags.md)

## コンテキスト

- タグは **filename / auto_tagger / auto_d1 / inferred_ja** など複数 source から来る。再バッチ（tagger・d1）で **機械 source は上書き**される。
- ユーザーが詳細で直した内容は **消えてはならない**（blueprint · 差分レイヤー）。
- Phase 2 まで **閲覧のみ**。Phase 3 の入口として **1 枚単位のタグ追加・非表示**を先に実装する。

## 決定

1. **機械 source は UI から書き換えない** — `filename` · `auto_tagger` · `auto_d1` · `inferred_ja` · レガシー `auto` の行を UPDATE/DELETE しない。
2. **手動は差分のみ** — 追加 → `manual_added`、表示から外す → `manual_removed`（タグ文字列単位。source 横断）。
3. **表示タグ** — 既存 `effective_tags()` / 検索 SQL と同じ式（[tags.md](../specs/tags.md)）。`manual_removed` に載ったタグは **どの source にあっても** 一覧・検索・詳細から除外。
4. **再タグ付け後** — tagger/d1 バッチは該当 source を replace するが **`manual_*` 行は触らない**（既存 ingest/jobs 方針を維持）。
5. **検索の正本** — 編集は DB のみ。クエリ文字列の意味は変えない（[query-language.md](../specs/query-language.md)）。編集後は **同じ `tag:` クエリでヒット集合が変わる**のは正常（データが変わったため）。
6. **Tag Bridge** — 手動追加タグも `manual_added` として保存。bridge の member に後から載せれば `tag:ラベル` 検索に含められる。DB 上の tagger 英語は依然変更しない。
7. **v1 スコープ** — 詳細画面の 1 枚編集 + PATCH API。一括・Undo スタック・タグ一括リネームは Phase 3 後半（別タスク）。
8. **正規化** — v1 は **trim + 空拒否** のみ。`tag_vocabulary` の alias 自動適用は v2 候補。

## 非採用

- 機械タグの「直接編集」（provenance 喪失 · 再バッチと競合）
- 削除を source 別に記録（複雑で UI 説明が難しい。タグ名単位の `manual_removed` で十分）
- 編集内容をクエリや localStorage にだけ持つ（サーバー DB が正本）

## 未決（v1 では固定）

| 項目 | v1 方針 |
|---|---|
| 非表示にしたタグの一覧 UI | 折りたたみ「非表示にしたタグ」+ 復元ボタン（推奨） |
| `種類/` 等 namespace の手動追加 | 許可（`種類/イラスト` 文字列として `manual_added`） |
| 予約タグ `route/*` の手動追加 | 400 で拒否 |
| FTS / 索引更新 | PATCH 成功時に当該 image の tags 列を更新（実装計画 T1） |

## 関連

- [phase-3.md](../plans/phase-3.md) — 3.1 TagEditor
- [api.md](../specs/api.md) — PATCH tags
