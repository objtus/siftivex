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
| `光の方向/` | 順光, 逆光, 側光, 上光, 下光 | 確定（2026-09-07） |
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
- **thinking**: デフォルト無効（`enable_thinking: false`）。試行錯誤時は `thinking_budget_tokens` + `max_thinking_chars` で短い think を有効化可（遅くなる）

### タグ生成のソース（2026-10 移行後）

| 層 | source | 語彙 | 由来 |
|---|---|---|---|
| ファイル名タグ | `filename` | **日本語** | 取り込み前の確定タグ — **上書きしない** |
| booru tagger | `auto_tagger` | **英語** | cl_tagger ONNX — 全件（[findings](../plans/model-stack-pilot-findings.md)） |
| namespace 判定 | `auto_d1` | 日本語 `種類/`… | d1-3B choice |
| 推定 flat JA | `inferred_ja` | 日本語 | d1 + master 語彙（[rollout](../plans/model-stack-rollout.md) フェーズ C） |
| ~~VLM タグ~~ | ~~`auto`~~ | — | **廃止** — [tag-stack-migration.md](../plans/tag-stack-migration.md) M0 で削除 |
| VLM キャプション | （列 `vlm_caption`） | 自然言語 | オンデマンドのみ。タグ source には載せない |

**filename と tagger は統合しない。** 日本語 UI 検索は filename + namespace、density・英語軸は tagger。低 Jaccard は正常。

**Tag Bridge**（英日の実用エントリのみ）: 検索 OR 展開・表示ラベル — [tag-bridge.md](../decisions/tag-bridge.md) · [仕様](tag-bridge.md)。DB の tagger 文字列は書き換えない。

移行後のパイプライン: **filename + auto_tagger + auto_d1 (+ inferred_ja)**。実施順は [tag-stack-migration.md](../plans/tag-stack-migration.md)。

**d1 拡張（計画）**: DB `filename` を一度集計し master 日本語語彙を作る（足す・間引く）。d1 はそのリストから該当タグを choice/noul で選び **`inferred_ja`** として保存（filename 非上書き）。tagger 英語を state に載せて連絡。詳細 → [model-stack-rollout.md](../plans/model-stack-rollout.md)。

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
表示タグ = ∪(filename, auto_tagger, auto_d1, inferred_ja, …) + manual_added − manual_removed
```

（実装移行中: `search.py` / `effective_tags` はまだ `auto` を参照している場合あり — M3 で更新。）

| 操作 | 書き込み先 | 再タグ（tagger/d1）時 |
|---|---|---|
| タグ追加 | `manual_added` | 保持 |
| タグ削除 | `manual_removed` | 保持 |
| 再タグ付け | 対象 **source** を replace | manual レイヤーは不変 |

## 一括リネーム

「紫系」→「パープル系」のようなタグ名変更。全画像に反映。
（TBD: API/UI の詳細）

## 関連ドキュメント

- [data-model.md](data-model.md) — タグの DB 表現
- [indexing.md](indexing.md) — VLM 実行タイミング
- [folder-rules.md](folder-rules.md) — route タグの自動付与
