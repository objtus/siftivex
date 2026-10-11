# タグ手動編集仕様

> **状態**: 草案（2026-10-12）  
> **決定**: [tag-editing.md](../decisions/tag-editing.md)  
> **参照**: [tags.md](tags.md), [data-model.md](data-model.md), [api.md](api.md), [ui.md](ui.md)

## 目的

1 枚の画像について、**表示されるタグ集合**をユーザーが調整する。機械生成タグを壊さず、再バッチ後も手動差分が残る。

## データモデル（再掲）

```
effective(image) =
  ⋃ { tag | source ∈ MACHINE ∪ { manual_added } }
  ∖ { tag | source = manual_removed }
```

| 区分 | source 値 |
|---|---|
| 機械（再バッチで replace されうる） | `filename`, `auto_tagger`, `auto_d1`, `inferred_ja`, レガシー `auto` |
| 手動 | `manual_added`, `manual_removed` |

実装: [tags_db.py](../../src/siftivex/tags_db.py) `effective_tags`, `tags_grouped_by_source`  
検索: [search.py](../../src/siftivex/search.py) — `manual_removed` を EXISTS から除外、`manual_added` を含む。

## 操作意味（論理）

| UI 操作 | DB 効果 | 備考 |
|---|---|---|
| **タグを追加** | `INSERT manual_added(tag)`。同 tag の `manual_removed` があれば **DELETE** | 既に effective にある tag は **no-op**（200） |
| **タグを非表示** | tag が `manual_added` のみなら **DELETE manual_added**。さらに **`INSERT manual_removed(tag)`** | 機械 source の行は残る |
| **非表示を元に戻す** | **`DELETE manual_removed(tag)`** | 機械側にまだ tag があれば再び表示。無ければ表示されない |
| **手動追加を取り消し** | `manual_added` の DELETE のみ | 「追加」したチップの × と同じ |

**タグ文字列**は image 内で一意に識別。`serafuku` を非表示にすると `auto_tagger:serafuku` も見えなくなる。

### 正規化（v1）

- 前後空白除去。空文字は 400。
- 最大長 200 文字（仮上限 · 実装時定数化）。
- 拒否: `route/` プレフィックスで始まるタグ（ルート予約）。

### 再タグ・ingest との関係

| イベント | manual_added | manual_removed | 機械 source |
|---|---|---|---|
| tagger バッチ | 不変 | 不変 | `auto_tagger` replace |
| d1 バッチ | 不変 | 不変 | `auto_d1` replace |
| ingest ファイル名 | 不変 | 不変 | `filename` replace |

## API

### `PATCH /api/images/{image_id}/tags`

**Body（JSON）**

```json
{
  "add": ["オリジナル", "種類/イラスト"],
  "remove": ["serafuku"],
  "restore": ["serafuku"]
}
```

| フィールド | 必須 | 説明 |
|---|---|---|
| `add` | no | 追加するタグ文字列の配列 |
| `remove` | no | 表示から外すタグ |
| `restore` | no | `manual_removed` から外す（再表示） |

少なくとも 1 つ非空。全て空 → 400。

**200** — 更新後の画像概要（`GET /api/images/{id}` と同型のタグ部分で可）:

```json
{
  "image_id": "img_…",
  "tag_sources": { "filename": [], "auto_tagger": [], "…": [], "manual_added": [], "manual_removed": [] },
  "tags": ["… effective …"]
}
```

**404** — 未知の `image_id`  
**400** — 検証エラー（空 tag · 予約 tag 等）

認証: v1 はローカル API 前提（127.0.0.1）。

### 将来（Phase 3 後半）

- `POST /api/images/bulk/tags` — 同 body を複数 ID に適用
- Idempotency-Key / 409 — 必要になったら

## UI（mockup → 本番 React）

### 配置

- **閲覧モード** `view` · 情報パネル `#detail-tags` の直下またはタグブロック内。
- Phase 2 の source 別折りたたみは維持。**編集モード**で effective タグに ×、末尾に入力 + 「追加」。

### 挙動

| 要素 | 動作 |
|---|---|
| 「タグを編集」トグル | 編集モード ON/OFF。OFF 時は Phase 2 表示（クリックで **検索**のみ） |
| 編集中のチップ × | `remove` API（非表示） |
| 入力 + Enter / 追加 | `add` API |
| 「非表示にしたタグ」 | `manual_removed` 一覧 · 行ごとに「表示に戻す」→ `restore` |
| 保存 | **即 PATCH**（v1 ドラフトなし）。成功で `tag_sources` 再描画 · 一覧の該当カード tags 更新 |
| API 未接続 | 編集 UI 非表示または disabled |

### 検索・Bridge との共存

- 閲覧時: 既存どおりチップクリック → `tag:<label>`（bridge）/ クエリ正本原則。
- 編集モード: チップクリックは **削除**優先（誤って filter しない）。または編集中は filter クリック無効。

## テスト観点

1. filename + tagger あり · `remove` tagger 語 → effective から消える · DB に `auto_tagger` 行は残る · `manual_removed` 1 行。
2. `add` 新規 → `manual_added` · effective に出る · `tag:その文字列` で検索ヒット。
3. `remove` 後 `restore` → effective 復帰。
4. `add` のみ存在する tag を `remove` → `manual_added` 消え、effective から消える（`manual_removed` 不要）。
5. tagger 再実行後も `manual_*` 不変 · `remove` 済み tag は再出現しない。

## 関連

- [query-language.md](query-language.md) — `tag:=` / bridge
- [tag-bridge.md](tag-bridge.md) — `manual_added` を member に含められる
