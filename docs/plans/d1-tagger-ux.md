# d1 と tagger — パイプラインと UI の整理

## いま d1 に何を渡しているか

画像本体 + 固定の質問セット + **filename 由来タグ**（テキスト state）。**auto_tagger は渡さない。**

| 入力 | 内容 |
|------|------|
| **画像** | `source_path` を d1 にそのまま入力 |
| **questions** | `build_d1_question_set()` — 各 namespace（種類/画角/…）の **choice 1 問** + config の追加 yes/no 等 |
| **state（テキスト）** | `filename_hint_state()` — **under 旧ファイル名**（`IMG4239_毛-うんこ.JPG` 形式）から取った `source=filename` タグだけ。ハイフン順で **全件**（`filename_hint_limit: 0`） |

例: `filename tags: 毛, うんこ`

**pixiv の filename タグは渡さない**（`オリジナル`, `SF`, `なにこれ切ない` 等は DB 検索用のみ。d1 には `state=None`）。

```text
runner.decide(path, questions, state_text=state)
→ namespace_tags_from_d1(out, min_choice_prob=…)
→ replace_auto_d1_namespace → source=auto_d1（例: 種類/写真）
```

### 設定（`config/model_stack_pilot.yaml`）

| キー | 意味 |
|------|------|
| `state_hint_source: filename` | filename タグを state に（既定） |
| `state_hint_source: none` | ヒントなし（vision + 質問のみ） |
| `filename_hint_limit: 0` | 全 filename タグ |
| `filename_hint_limit: -1` | 同上 none（文字列を渡さない） |
| `filename_hint_limit: N>0` | 先頭 N 件まで |

### 「ヒントなし」

`state_text=None` — 画像と質問だけ。d1 バッチでは `state_hint_source: none` または `filename_hint_limit: -1`。

### バッチ対象

既定はルート内の **active 全件**（pixiv も state なしで d1 実行可）。**tagger 完了は不要**。

`--require-legacy-filename` — under 形式ファイル名だけに限定（ヒント付き画像だけ再処理したいとき）。

under 約 3924 枚のうち legacy filename タグありは約 2252 枚 — 残りはタグ区画なし等（d1 は画像+質問のみ）。

## tagger との役割分担

| source | 用途 |
|--------|------|
| `filename` | under 手動 + pixiv タグ → **検索**；d1 state は **under 旧ファイル名分のみ** |
| `auto_tagger` | Danbooru EN → **検索のみ**（d1 には渡さない） |
| `auto_d1` | 構造化 namespace 出力 |

## mockup で混在して見える理由

| 場所 | 表示 |
|------|------|
| **一覧・表** | `item.tags` = `effective_tags()`（全 source マージ） |
| **詳細（API）** | `tag_sources` ごとに `<details>` 分離 |

## 関連コード

- `src/siftivex/d1_namespace.py` — `filename_hint_state`, `ordered_filename_tags`, `d1_state_text_from_config`
- `scripts/d1_batch.py`
- `src/siftivex/tags_db.py` — `apply_filename_tags`
