# モデルスタック評価 — 走り書きメモ

> きれいに書かない。最終整理は [model-stack-pilot-findings.md](model-stack-pilot-findings.md)。

## 2026-10-10

- フェーズ 0 実装: `siftivex/pilot/*`, `scripts/model_stack_pilot.py` 拡張, `export_pilot_gold.py`, `generate_pilot_review.py`, `pilot_search_compare.py`, `analyze_pilot_d1.py`
- optional deps: `pip install -e ".[embed,pilot]"`
- G30/G50: `python scripts/export_pilot_gold.py`
- CLIP baseline: `python scripts/model_stack_pilot.py --manifest data/phase0/manifest.json --backends clip_embed`
- tagger: `--backends tagger_cl --download-models --limit N`
- d1: `--backends d1_3b --download-models --limit N`
- gemma2: `--backends embedding_gemma2 --download-models --limit N`（検索比較は `--store-vectors` で clip+gemma 後 `pilot_search_compare.py`）
- ハードウェアは JSON の `hardware` フィールドを参照

### smoke 結果（2026-10-10 server）

- **CLIP** M300 の 5 枚: ~0.32s total → `model_stack_pilot_20261010T045410Z.json`
- **cl_tagger** 1 枚: 1.9s, provider CUDA EP, 64 tags（例: underwear, 1girl, photo medium）→ `...045517Z.json`
- **d1-3B** GPU OOM（他プロセスで VRAM 逼迫）→ `CUDA_VISIBLE_DEVICES=` CPU で 1 枚 **123s** → `...045916Z.json`。本番は GPU 単独載せ or `prefer_cuda: true`
- **EmbeddingGemma 2** GPU OOM → CPU 1 枚 **3.0s** → `...050039Z.json`。`transformers>=5.19` 必要
- G30/G50: `data/phase0/gold/g30.json`, `g50_d1.json`（pool 292）

### GPU 空き後バッチ（2026-10-10 · RTX 5060 Ti · config/model_stack_pilot.yaml）

|  run | 枚数 | 時間 | 秒/枚 | 出力 |
|---|---:|---:|---:|---|
| CLIP M300 | 299 ok / 1 missing | 11.7s | ~0.04 | `model_stack_pilot_clip_m300.json` |
| cl_tagger M300 | 299 / 1 | 532s | ~1.78 | `model_stack_pilot_tagger_m300.json` |
| d1 G50 GPU | 50 | 24.2s | **~0.48** | `model_stack_pilot_d1_g50_gpu.json` |
| Gemma2 M300 | 296 / 4 err | 35.7s | ~0.12 | `model_stack_pilot_gemma_m300.json` |
| CLIP+Gemma search | 79 | — | — | `model_stack_pilot_search80.json` + `pilot_search_compare.json` |

- **tagger vs VLM auto**（booru 英語 vs 日本語 flat）Jaccard 平均 **0.003** — 語彙が別物なので低いのは想定内。目視は `pilot_tagger_m300_sample.html`
- **d1 vs 弱正解（VLM namespace）** G50: 種類/ **98%**, 人数/ 67%, アングル/ 60%, 画角/ 58% → `pilot_d1_analysis_g50.json`
- **検索プローブ** 80 枚: 両方とも under.iphone 実写寄りで Top5 が似るが、`制服`/`school uniform` は Gemma が filename 寄りタグに当たりやすい印象（要目視メモ）
- **legacy VLM V10**: llama-server 8081 未起動のためスキップ

### 残タスク完了（2026-10-10）

- [x] G30 HTML: `data/phase0/review/pilot_g30_review.html`（filename / tagger / VLM 並列 + メモ欄）
- [x] d1 ablation G50: `pilot_d1_ablation_g50.json`（none / tagger / filename — 人数・画角で tagger 微増）
- [x] 統合 10 例: `docs/plans/pilot_integration_stories.json`
- [x] findings: [model-stack-pilot-findings.md](model-stack-pilot-findings.md)
- [x] VLM V10 試行: llama :8081 未応答 → 10/10 err（`model_stack_pilot_vlm_v10.json`）

### 任意フォロー

- [ ] G30 各カードの textarea に目視メモ（ブラウザで保存は手動）
- [ ] llama 起動後 V10 再実行
- [ ] Camie tagger 比較（第2波）
