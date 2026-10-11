# クエリ言語

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §クエリ構文, §タグによる複雑な条件検索, §並び替えコンテキスト

## 概要

ユーザーが入力するクエリ文字列を、バックエンドの検索処理（SQLite FTS5 + LanceDB ANN）に変換するための仕様。

## トークン一覧

| トークン | 例 | 意味 |
|---|---|---|
| `tag:` | `tag:vaporwave系` | タグを含む（**Tag Bridge** ラベルも可 → [tag-bridge.md](tag-bridge.md)） |
| `-tag:` | `-tag:未分類` | タグを除外 |
| `album:` | `album:参考資料` | アルバム所属 |
| `similar_to:` | `similar_to:img_xxxx` | 基準画像との類似 |
| 自然言語 | `青い髪の女の子` | embedding 意味検索 |
| `archived:` | `archived:true` | アーカイブ状態 |

## 構文規則

（TBD: 正式な BNF または例ベースの定義）

### 論理演算

- `AND` / `OR` / `-`（NOT 相当）
- 括弧による入れ子: `(A OR B) AND NOT C`

### ボタン操作との同期制約

blueprint より:

> ボタン操作で組み立てられるクエリは「含むタグを AND/OR でまとめ、除外タグを AND で付加する」単純構造に限られる。
> 複雑な入れ子はクエリ欄のみで表現可能。ボタン側はベストエフォート + 控えめな注記。

（TBD: 同期アルゴリズムの詳細）

## Tag Bridge（橋渡しラベル）

[tag-bridge.md](tag-bridge.md) · [決定](../decisions/tag-bridge.md)

ユーザーが `tag:制服` のように入力したとき、API は `data/tag_bridge.json` を参照する。

1. `label === "制服"` のエントリがあれば、`members` を **OR** で include 集合に展開する。  
   例: `filename:制服` OR `auto_tagger:serafuku` OR `auto_tagger:school_uniform`
2. エントリが無ければ、`制服` を通常の 1 タグ（全 source 対象の既存ルール）として扱う。
3. 複数の `tag:` / `include_tag` は展開 **後** も **AND**（従来どおり）。
4. `-tag:` は v1 では bridge 非対応（リテラルタグのみ除外）。

**UI**: 代表ラベルは日本語を推奨。詳細の英語 Tagger チップには bridge があれば括弧で label を表示（DB は変更しない）。

## FTS5 への変換

（TBD: タグ・OCR 検索の FTS5 クエリ生成規則。bridge 展開は FTS 前段で include 集合を確定）

## LanceDB への変換

（TBD: 自然言語クエリ → embedding → ANN 検索）

### フィルタ付きベクトル検索

タグ/album 等のメタデータフィルタとベクトル検索を 1 クエリで実行する方式。

（TBD）

## 並び替え

| モード | 条件 | ソートキー |
|---|---|---|
| デフォルト | 常時 | ファイル名順 |
| 関連度順 | 自然言語クエリあり | embedding 距離スコア |
| 類似画像 | `similar_to:` あり | 基準画像との距離スコア |
| カラムソート | 詳細リスト表示時 | 名前/更新日/タグ数/サイズ |

（TBD: 各モードの API パラメータ）

## デバウンス

クエリ欄入力は 200〜300ms デバウンス後に検索実行。

## 関連ドキュメント

- [data-model.md](data-model.md) — FTS5 テーブル定義
- [api.md](api.md) — 検索 API エンドポイント
- [ui.md](ui.md) — FilterBar, QueryInput, TagChip
- [tag-bridge.md](tag-bridge.md) — 辞書ファイル・API
