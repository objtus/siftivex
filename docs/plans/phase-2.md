# Phase 2: 検索・閲覧の最小 UI

> **状態**: 着手 — mockup v3 が参照実装（2026-10-12）  
> **参照**: [project-roadmap.md](project-roadmap.md), [tag-stack-migration.md](tag-stack-migration.md), [ui.md](../specs/ui.md)

## 目的

フィルタ（タグ/自然言語）→ グリッド → 詳細の統一モデルを動かし、「実用に耐えるか」を検証する。

**前提**: タグ検索の中身は **filename + auto_tagger + auto_d1**（VLM `auto` は使わない）。

## 前提条件

- [x] Phase 1 完了（2026-09-06）
- [x] 索引 v2 **M0〜M2**（本番 DB）
- [~] 索引 v2 **M3**（検索/API/索引 UI — おおむね完了 · ingest 増分は残）
- [~] [ui.md](../specs/ui.md) — **mockup v3 準拠で草案確定**（React 未）
- [ ] [query-language.md](../specs/query-language.md) 確定
- [ ] [api.md](../specs/api.md) 検索・一覧エンドポイント確定

## スコープ

### In

- **mockup v3**（現行）またはのち React 昇格
- 検索 API（タグ + 自然言語 + OCR）
- 一覧・詳細、サイドバーフィルタ、**source 別タグ表示**
- レスポンシブ（PC / tablet / phone）
- レイアウト切替（行揃え / masonry / 正方形 / 表）
- Tagger / d1 バッチ進捗（2.9 · 設定ドロワー）

### Out（Phase 2）

- タグ編集 · OCR 編集 · アルバム · 一括操作
- 類似画像パネル · VLM キャプション UI（→ 2.8 / Phase 3 寄り）
- 本番 React 必須（mockup で検証後に判断）

## タスク

| # | タスク | 状態 | 備考 |
|---|---|---|---|
| **—** | mockup v3 UI | **done** | [mockup-design-v3.md](mockup-design-v3.md) |
| **—** | 索引 v2 M0〜M2 | **done** | 40,305 枚 tagger+d1 |
| **—** | M3 索引/API | **ほぼ完了** | status API · tag_sources · FTS 新 source |
| 2.1 | React + Vite プロジェクト | pending | mockup 昇格タイミングで |
| 2.2 | 検索 API | in progress | 実 API 利用中 · 仕様書は未確定 |
| 2.3 | 画像配信 API | done | |
| 2.4 | FilterBar + QueryInput | **mockup done** | sidebar + 検索欄 |
| 2.5 | ImageGrid + 大規模一覧 | in progress | ページング ✅ · 仮想スクロール未 |
| 2.6 | DetailScreen + 前後移動 | **mockup done** | tag_sources · page strip |
| 2.7 | 実利用検証 | **進行中** | [mockup-phase2.md](mockup-phase2.md) |
| 2.9 | Tagger / d1 進捗 UI + API | done | 設定 → 索引の状況 |
| 2.8 | VLM キャプション UI | pending | [vlm-on-demand.md](../decisions/vlm-on-demand.md) |

## 完了条件

- [ ] **filename + auto_tagger** で pixiv / under.iphone をタグ検索できる
- [x] 詳細で source 別タグが分かる（mockup）
- [ ] タグフィルタで数千枚を絞り込める（要チェックリスト確認）
- [ ] 自然言語（CLIP）検索が動く
- [ ] 資料探しで「使える/使えない」判断ができる

## 関連ドキュメント

- [mockup-phase2.md](mockup-phase2.md) — 検証手順
- [query-language.md](../specs/query-language.md)
- [api.md](../specs/api.md)
- [ui.md](../specs/ui.md)
- [model-stack-rollout.md](model-stack-rollout.md)
