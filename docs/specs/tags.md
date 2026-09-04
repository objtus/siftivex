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
| `身体部位/` | （Phase 1 では未追加） | flat タグで代替 → [OQ-001](../open-questions.md) |
| `画角/` | 全身, 上半身, バストアップ, 顔アップ, パーツクローズアップ | 確定 |
| `アングル/` | 正面, 側面, 背面, 俯瞰, あおり | 確定 |
| `人数/` | 0人(物・背景のみ), 1人, 2人, 3人以上 | 確定 |

### フラットタグ

衣装、髪型、表情、構図の特徴、素材感など。

- **優先語彙**: ファイル名タグから自動生成（`config/tag_vocabulary.yaml`）
- VLM は優先語彙を exact match で使う（システムプロンプトに注入）
- 語彙に無い概念も追加可。**上限**: `config/vlm.yaml` の `max_flat_tags`（デフォルト 60）
- 表記ゆれは `aliases` で手動統合 → 再生成
- `namespace_tags` と重複する flat タグは `exclude_flat_tags` で除外（例: `2D` → `種類/`）

### タグの意味（tag_notes）

多義語や namespace と重複しやすい語は `tag_notes` で VLM に明示する。定義の実体は gitignore された `config/tag_vocabulary.yaml` に置く。

| タグ | 意味（例） |
|---|---|
| 2D | flat 不可 → `種類/`（イラスト等）で表現 |
| 修正 | 画像加工全般 |

### 優先語彙（tag_vocabulary）

```bash
make build-vocabulary   # under.iphone 全件スキャン → config/tag_vocabulary.yaml
```

| ファイル | 内容 |
|---|---|
| `config/tag_vocabulary.yaml` | 生成物（gitignore） |
| `config/tag_vocabulary.yaml.example` | スキーマ例 + manual_flat_tags |

生成後、VLM プロンプトの【優先語彙】ブロックに反映される。
ファイル名タグは正規化後 **priority_tags** として毎画像に渡す。

→ 実装: [tag_vocabulary.py](../../src/siftivex/tag_vocabulary.py), [build_tag_vocabulary.py](../../scripts/build_tag_vocabulary.py)

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
| `未分類` | VLM 成功だが namespace + flat が空 | 自動 |
| `要再タグ` | VLM 失敗（JSON 不正等） | 自動。`vlm_tag.py --retry-errors` |

レビュー時は `tag:要再タグ OR tag:未分類` でフィルタ。

## VLM プロンプト

- **モデル**: Qwen3.6 35B（llama.cpp / port 8081）
- **設定**: `config/vlm.yaml`（`max_tokens`, `max_flat_tags` 等）
- **thinking**: 無効（`enable_thinking: false`）

### タグ生成の2層

| 層 | source | 由来 |
|---|---|---|
| ファイル名タグ | `filename` | 旧自作アーカイブ形式パーサー（参考・保持） |
| VLM タグ | `auto` | Qwen VLM が画像から生成（namespace + flat） |

ファイル名タグは正規化後 **priority_tags** として VLM に渡す。VLM 再実行時も `filename` ソースとして保持。

### ファイル名パーサー（under.iphone / 旧形式）

```
IMG3078_2D-背景-空.JPG       → 2D, 背景, 空
IMG_0265-建物-夕方-横.JPG    → 建物, 夕方, 横
15283_1-風景-山-雲.jpg       → 風景, 山, 雲
```

→ 実装: [filename_tags.py](../../src/siftivex/filename_tags.py), [under_iphone_legacy_v1.yaml](../../config/parsers/under_iphone_legacy_v1.yaml)

### 出力形式

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
