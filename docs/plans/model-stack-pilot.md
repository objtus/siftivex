# モデルスタック比較パイロット（数百枚）

> **状態**: 草案  
> **ADR**: [role-based-model-stack.md](../decisions/role-based-model-stack.md)

## 目的

VLM 一括タグから **役割別スタック**へ移行する前に、同じ画像集合で次を記録する。

1. **スループット**（枚/秒、VRAM、失敗率）
2. **出力の中身**（tagger タグ分布、d1 の確率、embed の次元）
3. **目視用レビュー**（HTML または既存 phase0 review 形式）

## 入力

| 方法 | コマンド例 |
|---|---|
| Phase 0 manifest | `scripts/model_stack_pilot.py --manifest data/phase0/manifest.json` |
| 件数上限（DB） | `scripts/model_stack_pilot.py --from-db --limit 300` |
| パスリスト | `scripts/model_stack_pilot.py --paths-file paths.txt` |

## バックエンド（段階的に有効化）

| ID | 状態 | 説明 |
|---|---|---|
| `clip_embed` | **実装済** | 現行 OpenCLIP。baseline 速度 |
| `legacy_vlm` | 任意 | 現行 `VlmClient`（`--include-legacy-vlm`）。遅いので少数推奨 |
| `tagger_cl` | **実装済** | cella110n/cl_tagger ONNX（`--download-models`） |
| `embedding_gemma2` | **実装済** | sentence-transformers + bf16/fp32 |
| `d1_3b` | **実装済** | LiquidAI d1-3B + `NAMESPACE_OPTIONS` から choice 生成 |

補助: `export_pilot_gold.py`, `generate_pilot_review.py`, `analyze_pilot_d1.py`, `analyze_pilot_tagger.py`, `pilot_search_compare.py`  
メモ: [model-stack-pilot-memo.md](model-stack-pilot-memo.md)

## 設定

`config/model_stack_pilot.yaml.example` をコピーして質問セット・tagger 閾値を編集する。

```yaml
decision_questions:
  - id: genre_photo_vs_illust
    prompt: "この画像は実写写真ですか？"
    type: yes_no
  - id: quality_keep
    prompt: "アーカイブに残す品質ですか？"
    type: yes_no
```

## 出力

`data/phase0/results/model_stack_pilot_<timestamp>.json`:

```json
{
  "manifest": "...",
  "backends": {
    "clip_embed": { "images": 300, "total_sec": 12.4, "errors": 0 },
    "tagger_cl": { "status": "skipped", "reason": "not implemented" }
  },
  "per_image": [
    {
      "source_path": "/path/to/a.jpg",
      "clip_embed_sec": 0.04,
      "tagger_tags": null,
      "d1": null
    }
  ]
}
```

目視用は `scripts/generate_review.py` との連携を後続タスクとする（tagger 列を追加）。

## 推奨手順

1. manifest 300 枚程度を固定（seed 固定で再現可能に）。
2. `clip_embed` のみ実行 → GPU/CPU 時間の baseline。
3. cl_tagger を ONNX Runtime で 1 枚 → 300 枚とスケール確認。
4. EmbeddingGemma 2 を 50 枚サンプル → bf16/fp32 と VRAM。
5. d1-3B を同 50 枚 + 質問 3〜5 個 → 確率の顔付き確認。
6. 問題なければ tagger 全件 → embed 全件 → d1 はルート別サンプリング。

## ハードウェアメモ（4060 Ti）

- tagger ONNX と embed を **同時常駐**するか **直列**するかでピーク VRAM が変わる。パイロット JSON に `peak_vram_mb` を足す予定。
- d1-3B は 4090 17ms の報告のみ。**4060 Ti は実測必須**。

## 関連コマンド

```bash
# baseline（CLIP のみ）
.venv/bin/python scripts/model_stack_pilot.py --manifest data/phase0/manifest.json --backends clip_embed

# レガシー VLM を 10 枚だけ比較
.venv/bin/python scripts/model_stack_pilot.py --from-db --limit 10 --backends clip_embed,legacy_vlm --include-legacy-vlm
```
