# タグ仕様

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §タグの構造, §タグ付け方式の方針, §タグ・OCRの手動修正

## 概要

タグの種類（名前空間/フラット/ルート）、VLM への入力仕様、手動編集ルール。

## タグの種類

### 名前空間タグ（閉じたリスト）

`namespace/value` 形式。VLM に固定リストから選択させる。

| 名前空間 | 値（確定分） | 状態 |
|---|---|---|
| `種類/` | 写真, イラスト, 3DCG, 図解/資料, 文章/スクショ, 漫画コマ, ピクセルアート | 確定 |
| `身体部位/` | TBD | → [OQ-001](../open-questions.md) |
| `画角/` | 全身, 上半身, バストアップ, 顔アップ, パーツクローズアップ | 確定 |
| `アングル/` | 正面, 側面, 背面, 俯瞰, あおり | 確定 |
| `人数/` | 0人(物・背景のみ), 1人, 2人, 3人以上 | 確定 |

### フラットタグ

衣装、髪型、表情、構図の特徴、素材感など。VLM が自由生成。
表記ゆれは一括リネーム操作で運用カバー。

### ルートタグ（予約）

取り込みルート由来。フォルダルールで自動付与。

| タグ | 意味 |
|---|---|
| `route/pixiv` | pixiv ダウンローダー経由 |
| `route/legacy` | 旧自作アーカイブ |
| `route/web` | Twitter/Google/Pinterest 等 |
| `route/under-iphone` | NAS under.iphone アーカイブ |
| `route/icloud` | iCloud Photos（後回し） |

（TBD: 完全なリスト）

### 予約タグ

| タグ | 意味 | 付与方法 |
|---|---|---|
| `未分類` | VLM タグ付け未確定 | 自動（条件 TBD → [OQ-004](../open-questions.md)） |

## VLM プロンプト

（TBD: システムプロンプト全文、JSON 出力形式、temperature 等）

### 出力形式（草案）

```json
{
  "namespace_tags": {
    "種類/": "イラスト",
    "画角/": "全身",
    ...
  },
  "flat_tags": ["セーラー服", "ツインテール", ...],
  "caption": "..."
}
```

## 差分レイヤー（手動編集）

```
表示タグ = auto_tags + manual_added − manual_removed
```

| 操作 | 書き込み先 | VLM 再実行時 |
|---|---|---|
| タグ追加 | `manual_added` | 保持 |
| タグ削除 | `manual_removed` | 保持（再提案も抑制） |
| 再タグ付け | `auto_tags` 上書き | manual レイヤーは不変 |

## 一括リネーム

「紫系」→「パープル系」のようなタグ名変更。全画像に反映。
（TBD: API/UI の詳細）

## 関連ドキュメント

- [data-model.md](data-model.md) — タグの DB 表現
- [indexing.md](indexing.md) — VLM 実行タイミング
- [folder-rules.md](folder-rules.md) — route タグの自動付与
