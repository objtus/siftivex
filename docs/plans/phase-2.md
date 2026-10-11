# Phase 2: 検索・閲覧の最小 UI

> **状態**: 着手 — **索引 v2（M0〜M3）を UI より優先**（2026-10-10）  
> **参照**: [project-roadmap.md](project-roadmap.md), [tag-stack-migration.md](tag-stack-migration.md)

## 目的

フィルタ（タグ/自然言語）→ グリッド → 詳細の統一モデルを動かし、「実用に耐えるか」を検証する。

**前提**: タグ検索の中身は **filename + auto_tagger + auto_d1**（VLM `auto` は使わない）。M1/M3 完了後に Phase 2 完了条件を満たしやすい。

## 前提条件

- [x] Phase 1 完了（2026-09-06）
- [ ] [tag-stack-migration.md](tag-stack-migration.md) M0〜M3（索引 v2）
- [ ] [query-language.md](../specs/query-language.md) 確定
- [ ] [api.md](../specs/api.md) 検索・一覧エンドポイント確定
- [ ] [ui.md](../specs/ui.md) ListScreen / DetailScreen 確定

## スコープ

### In

- React + Vite プロジェクト（または mockup 昇格）
- 検索 API（タグ + 自然言語 + OCR）
- 一覧・詳細、FilterBar、**source 別タグ表示**
- Tagger / d1 バッチ進捗（2.9）

### Out

- マゾンリー、編集、アルバム、類似画像、レスポンシブ

## タスク

| # | タスク | 状態 | 備考 |
|---|---|---|---|
| **—** | **索引 v2 M0〜M3** | **ほぼ完了** | mockup 検証 → [mockup-phase2.md](mockup-phase2.md) |
| 2.1 | React + Vite プロジェクト作成 | pending | mockup 並行可 |
| 2.2 | 検索 API 実装 | in progress | M3 で `auto_tagger` 等を FTS に |
| 2.3 | 画像配信 API | done | |
| 2.4 | FilterBar + QueryInput | pending | |
| 2.5 | ImageGrid + 仮想スクロール | pending | |
| 2.6 | DetailScreen + 前後移動 | pending | tag_sources 表示 |
| 2.7 | 実利用検証 | pending | M1 後のタグで実施 |
| 2.9 | Tagger / d1 バッチ UI + API | in progress | mockup Lab 索引ステータス ✅ |
| 2.8 | VLM キャプション UI（タグなし） | pending | [vlm-on-demand.md](../decisions/vlm-on-demand.md) |

## 完了条件

- [ ] **filename + auto_tagger** で pixiv / under.iphone をタグ検索できる（M1+M3）
- [ ] 詳細で source 別タグが分かる
- [ ] タグフィルタで数千枚を絞り込める
- [ ] 自然言語（CLIP）検索が動く
- [ ] 資料探しで「使える/使えない」判断ができる

## 関連ドキュメント

- [query-language.md](../specs/query-language.md)
- [api.md](../specs/api.md)
- [ui.md](../specs/ui.md)
- [model-stack-rollout.md](model-stack-rollout.md)
