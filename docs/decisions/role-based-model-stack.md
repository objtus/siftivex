# ADR: 役割別モデルスタック（VLM 一括タグからの再設計）

- **日付**: 2026-10-10（移行計画 同日追記）
- **状態**: proposed（パイロット go — **実装は [tag-stack-migration.md](../plans/tag-stack-migration.md)**）
- **関連**: [blueprint.md](../../blueprint.md) §タグ付け・OCR, [vlm-on-demand.md](vlm-on-demand.md), [tag-quality-review.md](../tag-quality-review.md), [model-stack-pilot.md](../plans/model-stack-pilot.md)

## コンテキスト

Phase 0/1 では **汎用 VLM + 固定語彙プロンプト** で `auto` タグを生成してきた。運用と品質レビューの結果、次の問題が顕在化した。

- **速度**: 1 枚あたり数十秒規模。4 万枚の主役には向かない（オンデマンド運用に切り替え済み）。
- **品質**: JSON 破損・語彙外タグ・namespace との不整合。プロンプトと post-process で改善できるが、**アニメ・イラストの細粒度タグ**は VLM より **booru 系 tagger** の方が得意な領域が多い。
- **検索**: 現状 CLIP（OpenCLIP）で十分動いているが、テキスト・画像を同一空間に載せる **EmbeddingGemma 2** 等の選択肢が 2026 年に増えた。
- **独自基準**: 「このコレクションでは雰囲気 A か B か」「品質ゲート」など、**較正された yes/no・スコア**が欲しい。汎用 VLM の自由記述より **decision model** 系が適合しうる。

以上より、**1 本の VLM にタグ・埋め込み・判定を任せる構成**を見直し、役割別スタックを検討する。

## 決定（提案）

画像パイプラインを **4 層**に分ける。各層は独立に差し替え・閾値調整できる。

| 層 | 役割 | 候補 | 処理範囲 |
|---|---|---|---|
| **1. Tagger** | booru 系の細粒度タグ（属性・キャラ・作品・レーティング等） | cl_tagger (ONNX, Apache 2.0, ~42k tags), Camie Tagger v2, PixAI Tagger v0.9 | **全件**。閾値で採否 |
| **2. Embedding** | 類似検索・クラスタ・テキスト条件のゼロショット | **EmbeddingGemma 2** (740M, 768d, マルチモーダル)。現行 CLIP は比較・移行期の baseline | **全件**（初回バッチ + 増分） |
| **3. Decision** | **閉じた選択肢**からの判定（yes/no・単一/複数 choice・スコア）。**タグを自由生成しない** | **LiquidAI d1-3B**（本命: 画像+テキスト, 3.12B, RTX 4090 で ~17ms/枚の報告）。Vev 4B LoRA / SelfJev 4B Vision は Jev 互換だが画像転移に注意 | **namespace や独自基準など、候補が有限の問い** |
| **4. VLM** | キャプション・雰囲気の自然言語・例外説明 | Gemma 4 26B A4B 等（MoE, RAM 96GB オフロード想定）。現行 Qwen VL は **レガシー比較用**に残す | **必要な画像のみ** |

### 推奨パイプライン順

```
ingest → filename タグ
      → [1] tagger → auto_tagger_tags (新 source または auto のサブセット)
      → [2] embedding → LanceDB / 別テーブル
      → [3] d1 判定（設定された質問セット）
      → [4] VLM キャプション（キュー / オンデマンド）
```

Siftivex 既存概念との対応（**2026-10 確定** — [tags.md](../specs/tags.md)）:

- **tagger**: `source=auto_tagger`（`auto` に統合しない）。
- **namespace**: `source=auto_d1`（d1 choice）。VLM が付けた `auto` namespace は **M0 で削除**。
- **推定 flat JA**: `source=inferred_ja`（master 語彙 + d1、後続）。
- **VLM**: [vlm-on-demand.md](vlm-on-demand.md)。**タグ `auto` は廃止**。`vlm_caption` のみ。

### 3 層の役割分担（排他ではなく併用）

| コンポーネント | やること | やらないこと |
|---|---|---|
| **Tagger** | 画像から **大量の booru 系タグをスコア付きで生成**（全件・閾値） | namespace の厳密な単一選択、独自ルールの確率較正 |
| **EmbeddingGemma 2** | **ベクトル化** → 類似検索・クラスタ・テキストクエリ | タグ列の生成、UI 向けラベル付け |
| **d1-3B** | 画像（±短文コンテキスト）に対し **与えられた候補から選択 / yes-no / 段階スコア**（複数問を 1 パス、確率付き） | 自由記述タグの生成、4 万タグ語彙の探索 |

**d1 の典型的な使い方（Jev 代替）**

- 入力: **画像** +（任意で tagger 上位タグや OCR を state に含めてもよい）
- 質問: `type: choice` で `criteria: { "全身": "…", "バストアップ": "…" }` のように **候補名と説明の有限集合**
- 出力: `choice` + `probabilities`（または `noul` の P(yes)）— **出力トークンはゼロ**の decision API

→ 「タグリストの中からどれに該当するか」は **`choice`（単一選択）** または **独立なら複数の `noul`** で表現する理解でよい。  
→ ただし **cl_tagger の 4 万タグをそのまま 1 問に載せる**のは現実的ではない。**Siftivex の namespace（画角・種類・人数…）や、十〜数十件に絞った独自リスト**が d1 の想定サイズ。

Tagger で「候補を広く拾い」、d1 で「語彙 YAML 上の **閉じた軸**を確定」、Embedding で「探す」— という **三層併用**が ADR の意図どおり。

## 理由

| 要件 | VLM 単独 | 役割別スタック |
|---|---|---|
| 4 万枚のタグ密度 | 遅い・不安定 | Tagger が ONNX でスループット向き |
| アニメ・イラスト | プロンプト依存が大きい | Tagger はドメイン向け学習済みが多い |
| 類似検索 | CLIP で可 | EmbeddingGemma 2 でテキストクエリ拡張の余地 |
| 独自ルール（品質・ジャンル） | プロンプトで無理に表現 | d1 で確率付き判定 |
| 説明可能なキャプション | 得意 | VLM をスパースに使う |

## 候補モデルメモ

### 1. Tagger（booru 系）

- [cl_tagger](https://huggingface.co/Nonene/cl_tagger/blob/main/README.md): ONNX, Apache 2.0, 約 42,000 タグ。
- [Camie Tagger v2](https://huggingface.co/camais03/camie-tagger-v2)
- [PixAI Tagger v0.9](https://huggingface.co/)（ユーザー調査リスト）

### 2. EmbeddingGemma 2

- [google/embeddinggemma-2](https://huggingface.co/google/embeddinggemma-2): 2026-10-06 公開, 740M, 768 次元, テキスト・コード・画像・動画・音声。
- **注意**: float16 非対応 → **bf16 または fp32**。
- 初回回答で「テキスト専用」としていた点は **誤り**（マルチモーダル）。

### 3. Decision（Jev 系）

- **LiquidAI [d1-3B](https://huggingface.co/LiquidAI/d1-3B)**: decision model。画像+テキスト, transformers ≥ 5.14, ライセンス lfm1.0。複数質問 1 パス。
- **[vev-4b-lora](https://huggingface.co/CountingSheep/vev-4b-lora)**: Qwen3.5-4B ベース LoRA。
- **[selfjev-4b-vision](https://huggingface.co/Jwuthrich/selfjev-4b-vision)**: 学習分布外画像では転移弱い報告あり。
- Jev 本体・ホスト版 d1: テキスト専用または API 専用 → **ローカル画像一括には不向き**。

### 4. VLM

- [Gemma 4 26B A4B IT (NVIDIA NGC)](https://catalog.ngc.nvidia.com/orgs/nim/google/models/gemma-4-26b-a4b-it/-): アクティブ 3.8B MoE。96GB RAM オフロード想定。遅い → スパース運用。

## 代替案（採用見送り）

- **現状維持**: VLM + 語彙プロンプトのみ → 品質・速度の上限が低い。
- **VLM 二段構え**（blueprint 後乗せ案）→ 依然として tagger より遅く、細タグ精度も不利になりがち。
- **CLIP のみでタグ代替** → 分類閾値設計が重く、booru タグ体系と相性が悪い。

## パイロット実測（2026-10-10 · RTX 5060 Ti）

| 工程 | スループット | メモ |
|---|---|---|
| cl_tagger M300 | ~1.78 s/枚 | go — [findings](../plans/model-stack-pilot-findings.md) |
| d1 G50 | ~0.48 s/枚 GPU | namespace 種類/ 98% |
| EmbeddingGemma 2 M300 | ~0.12 s/枚 GPU | transformers≥5.19 |
| CLIP M300 | ~0.04 s/枚 | baseline |

### filename（日本語）と tagger（英語 booru）

- **共存・非統合**: filename は確定の日本語軸。tagger は英語 booru 密度。Jaccard 低いのは正常。
- **検索**: 両方インデックス。エイリアスは橋渡しのみ（filename を tagger で上書きしない）。
- **d1**: namespace 確定。state には tagger top-N ヒントが画角/人数でやや有効（ablation 参照）。

## 未確認（パイロットで潰す）

| 項目 | 内容 |
|---|---|
| アニメ・イラスト精度 | 公開ベンチは写真・一般画像中心。自前数百枚で目視 |
| マルチ GPU | ホスト **3 GPU** — 1 枚同載せ前提の OOM メモは **ピン留め並列**で緩和 → [gpu-workloads.md](../setup/gpu-workloads.md) |
| d1-3B の GGUF / llama.cpp | 未確認。動かない場合は transformers + GPU 直載せ |
| ライセンス | tagger / d1 / EmbeddingGemma 2 の商用・再配布条件を一覧化 |
| Siftivex 語彙との統合 | namespace タグを d1 に渡すか、tagger タグだけで検索するか |

**パイロット**: 完了 — [model-stack-pilot-findings.md](../plans/model-stack-pilot-findings.md)。  
**実装順**: [tag-stack-migration.md](../plans/tag-stack-migration.md)（M0 purge → M1 tagger → …）· [model-stack-rollout.md](../plans/model-stack-rollout.md)。

## 影響

- **blueprint.md** §タグ付け: 方針更新が必要（accepted 後）。
- **indexing.md**: 新ワーカー（tagger, embed v2, decision）のキュー設計。
- **Phase 2**: pixiv 36k の「VLM 一括」より **tagger 一括 + VLM スパース**が現実的。
- **既存データ**: VLM `auto` タグは **意図的に破棄**（品質・方針のやり直し）。CLIP は保持。再 embed（Gemma）は M5。

## 参考リンク

- [EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2)
- [LiquidAI/d1-3B](https://huggingface.co/LiquidAI/d1-3B)
- [vev-4b-lora](https://huggingface.co/CountingSheep/vev-4b-lora)
- [selfjev-4b-vision](https://huggingface.co/Jwuthrich/selfjev-4b-vision)
- [cl_tagger README](https://huggingface.co/Nonene/cl_tagger/blob/main/README.md)
- [Camie Tagger v2](https://huggingface.co/camais03/camie-tagger-v2)
