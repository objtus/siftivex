# Architecture Decision Records (ADR)

設計判断の記録。blueprint.md に既にある方針決定は ADR に起こす必要はない。
**blueprint 作成後に新たに判断したこと**、または**実装中に方針が変わったこと**を記録する。

## 一覧

| ID | タイトル | 日付 | 状態 |
|---|---|---|---|
| — | [ui-philosophy.md](ui-philosophy.md) — UI 設計思想（資料探し・二層ナビ） | 2026-09-06 | proposed |
| — | [vlm-on-demand.md](vlm-on-demand.md) — VLM オンデマンド | — | accepted |

## テンプレート

新規 ADR は `NNN-short-title.md` 形式で作成する。

```markdown
# ADR-NNN: タイトル

- **日付**: YYYY-MM-DD
- **状態**: proposed | accepted | deprecated | superseded
- **関連**: [spec へのリンク]

## コンテキスト

（何が問題だったか、なぜ判断が必要だったか）

## 決定

（何を選んだか）

## 理由

（なぜその選択をしたか）

## 代替案

（検討したが採用しなかった選択肢）

## 影響

（この決定が及ぼす影響、follow-up タスク）
```
