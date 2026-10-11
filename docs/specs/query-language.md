# クエリ言語

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §クエリ構文, §タグによる複雑な条件検索, §並び替えコンテキスト

## 概要

ユーザーが入力するクエリ文字列を、バックエンドの検索処理（SQLite FTS5 + LanceDB ANN）に変換するための仕様。

## トークン一覧

| トークン | 例 | 意味 |
|---|---|---|
| `tag:` | `tag:vaporwave系` | タグを含む（**Tag Bridge** ラベル一致時は OR 展開 → [tag-bridge.md](tag-bridge.md)） |
| `tag:=` | `tag:=serafuku` · `tag:="school uniform"` | **厳密** — bridge を使わずタグ名そのものだけ（全 source） |
| `-tag:` | `-tag:未分類` | タグを除外（v1 は bridge 非展開） |
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

### 検索意味の正本

**同じクエリ文字列**（と DB・`tag_bridge.json`）なら、クリック・キーボード・API の入口に関係なく **同じ結果** にする（[blueprint.md](../../blueprint.md) §タグによる複雑な条件検索 · クエリ欄同期）。

- フィルタの正本は **クエリ欄の文字列**（mockup は `GET /api/images?q=…` にそのまま載せる）。
- UI のチップ・ファセットは **クエリを編集するショートカット**。bridge に属する member をクリックしたときは **代表 `label` の `tag:ラベル`** をトグルする（`tag:serafuku` など member 文字列は載せない）。

### 展開規則

ユーザーが `tag:制服` のように入力したとき、API は `data/tag_bridge.json` を参照する。

1. **`tag:`（`=` なし）** — `label === "制服"` のエントリがあれば、`members` を **OR** で 1 つの include グループに展開。  
   例: `filename:制服` OR `auto_tagger:serafuku` OR …
2. エントリが無ければ、`制服` を通常の 1 タグ（全 source 対象）として扱う。
3. **`tag:=`（厳密）** — bridge **を見ない**。タグ名 1 件のみ（例: `tag:=serafuku` は tagger の serafuku だけ。`tag:制服` の OR にはならない）。
4. 複数 include トークンは展開 **後** も **AND**。
5. `-tag:` は v1 では bridge 非対応（リテラル除外のみ）。

**表示**: 代表ラベルは日本語を推奨。Tagger チップは `serafuku（制服）`。絞り込み中は bridge 経由の member も **include 表示**（クエリ上は `tag:制服` のまま）。

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
