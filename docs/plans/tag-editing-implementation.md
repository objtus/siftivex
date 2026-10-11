# タグ編集 実装計画

> **日付**: 2026-10-12  
> **仕様**: [specs/tag-editing.md](../specs/tag-editing.md) · **決定**: [decisions/tag-editing.md](../decisions/tag-editing.md)  
> **Phase**: [phase-3.md](phase-3.md) タスク 3.1  
> **方針**: v1 は **1 枚 · PATCH · mockup 詳細**。一括・Undo は 3.4–3.6 で追う。

## ゴール（v1 完了条件）

- [ ] `PATCH /api/images/{image_id}/tags` — `add` / `remove` / `restore` · 差分レイヤーのみ書き込み
- [ ] 単体テスト（仕様 §テスト観点 5 件）
- [ ] mockup 詳細: 編集モード · 追加 · 非表示 · 復元 · API 反映
- [ ] 手動: 1 枚編集 → 一覧 `tag:` 再検索で結果変化 · tagger バッチ後も手動差分保持（ステージング DB または本番 1 枚で可）

## 非ゴール（v1）

- 一括 PATCH · BulkActionBar
- Undo スタック（3.6）
- 機械 source の直接編集 · タグ一括リネーム
- OCR 編集（3.2）
- タグオートコンプリート API（`GET /api/tags`）
- 編集履歴監査ログ

---

## フェーズ一覧

| フェーズ | 内容 | 依存 |
|---|---|---|
| **T0** | 仕様・ADR（本計画） | — |
| **T1** | Python コア + PATCH API + tests | T0 |
| **T2** | mockup TagEditor UI | T1 |
| **T3** | 索引/FTS 整合 · ドキュメント確定 | T1 |
| **T4** | 一括 · Undo（Phase 3 後半） | T2 |

---

## T1 — バックエンド

**新規**: `src/siftivex/tag_edits.py`

| タスク | 詳細 |
|---|---|
| T1.1 | `normalize_manual_tag(raw) -> str` · 空/長さ/`route/` 拒否 |
| T1.2 | `apply_tag_patch(conn, image_id, *, add, remove, restore) -> TagPatchResult` |
| T1.3 | 上記 §操作意味の通りに SQL（トランザクション 1 本） |
| T1.4 | `patch_image_tags` を [api/app.py](../../src/siftivex/api/app.py) に追加 |
| T1.5 | レスポンス: `tags` + `tag_sources`（既存 detail ヘルパ再利用） |

**テスト**: `tests/test_tag_edits.py` — fixture は [test_tags_db.py](../../tests/test_tags_db.py) 流用。

**索引（T1.6 · 要調査）**

- ingest 時に tags を FTS/embed メタに載せている場合、PATCH 後に **当該 image だけ再同期**する関数を 1 本（無ければ T3 へ）。

---

## T2 — mockup UI

**変更**: [mockup/index.html](../../mockup/index.html), [mockup.css](../../mockup/mockup.css), [mockup.js](../../mockup/mockup.js)

| タスク | 詳細 |
|---|---|
| T2.1 | `#detail-tags` ヘッダに「タグを編集」トグル（`useApi` 時のみ） |
| T2.2 | `state.tagEditMode` · 編集中はチップ × · 追加 input |
| T2.3 | `patchImageTags({ add, remove, restore })` → PATCH → `renderDetailTags` + 一覧中の item 更新 |
| T2.4 | `manual_removed` 折りたたみ「非表示にしたタグ」+ 復元 |
| T2.5 | 編集モード中は `toggleTagFilterFromUi` 無効（クリック = remove） |
| T2.6 | エラー toast / `#detail-tags` 下メッセージ |

**UX メモ**

- 追加後も編集モード維持（連続入力）。
- Esc で編集モード終了（既存 Esc 優先順位: overlay → view 戻る — 編集モード OFF をその前に挿入可）。

---

## T3 — 仕上げ

| タスク | 詳細 |
|---|---|
| T3.1 | [data-model.md](../specs/data-model.md) — `image_tags.source` CHECK を実 DB（auto_tagger 等）と一致させる |
| T3.2 | [api.md](../specs/api.md) — PATCH 本文確定 |
| T3.3 | [tags.md](../specs/tags.md) — 差分レイヤー節から本仕様へリンク |
| T3.4 | [mockup-phase2.md](mockup-phase2.md) または新 **tag-editing-verify.md** に手動 3 ステップ |

---

## T4 — Phase 3 後半（参照のみ）

- `POST /api/images/bulk/tags`
- Undo: PATCH の逆操作をセッションスタック（最大 20）
- 未分類レビュー（3.7）— 編集 + 「次の未分類」ナビ

---

## 実装順（推奨）

```
T1.1–T1.5 + tests
  → curl PATCH 3 パターン
T2.1–T2.4
  → ブラウザ 1 枚編集
T3 ドキュメント · FTS があれば T1.6
```

**見積**: T1 1–2 日 · T2 1 日 · T3 半日（FTS 次第）。

---

## リスク

| リスク | 緩和 |
|---|---|
| 詳細と一覧の tags 不整合 | PATCH レスポンスで `apiImages` の該当 item を patch |
| bridge 表示と manual 追加 | 括弧 label は bridge 辞書のみ · manual 文字列はそのまま |
| 誤って機械タグ DELETE | API 層で source ホワイトリスト（manual のみ INSERT/DELETE） |

---

## リンク

- [project-roadmap.md](project-roadmap.md)
- [tag-bridge-implementation.md](tag-bridge-implementation.md)（完了 · 編集と独立）
