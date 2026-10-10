# GPU 配置（3 枚構成）

> **参照**: [blueprint.md](../../blueprint.md) §CLIP/VLM 分離, [indexing.md](../specs/indexing.md)  
> **実機確認**: 2026-10-10（`lspci` / `/proc/driver/nvidia/gpus/` / プロジェクト `.venv` の PyTorch）

---

## 実機マップ（このホスト）

CUDA の **index = `cuda:N` = `/dev/nvidiaN`**（PyTorch 確認済み）。

| `cuda` | PCI | 実 GPU | VRAM（PyTorch） | 主担当 |
|---:|---|---|---:|---|
| **0** | `01:00.0` | **GeForce RTX 5060 Ti** | **~15.5 GiB** | llama-swap / Qwen VLM · **d1-3B** 夜間 |
| **1** | `02:00.0` | **GeForce RTX 3060** | **~11.6 GiB** | **CLIP** cron · **EmbeddingGemma 2**（時間帯分離） |
| **2** | `03:00.0` | **GeForce RTX 2070 SUPER** | **~7.6 GiB** | **cl_tagger** ONNX（M1 pixiv バッチ） |

Intel UHD 630（`00:02.0`）は表示用。Siftivex 推論対象外。

### blueprint との対応

| blueprint の記述 | 実機 |
|---|---|
| VLM / llama-swap | **5060 Ti · cuda:0**（Phase 0 実測も VLM=cuda:0） |
| CLIP を「余っている GPU(3060/2070)」 | **3060 · cuda:1**（`SIFTIVEX_DEVICE=cuda:1` 既定） |
| 3 枚目 | **2070 SUPER · cuda:2** — tagger 等の軽〜中 ONNX |

[config/model_stack_pilot.yaml](../../config/model_stack_pilot.yaml) のピン留めは **このマップと一致**している（d1→0, Gemma→1, tagger→2）。

### 運用メモ

- **`nvidia-smi`**: 2026-10-10 時点で **Driver/library version mismatch**（NVML 595.99 vs カーネル側）。VRAM 監視は再起動後に `nvidia-smi` を再確認。PyTorch の `cuda` は動作していた。
- **d1 on cuda:2**（8 GiB）は **非推奨** — 3B bf16 単体でもきつい。**d1 は cuda:0**（VLM 停止時）。2070 は tagger 専用が安全。

---

## 原則

1. **1 GPU = 1 系統の重い推論**（同 GPU 上で VLM + d1 + Gemma を同時常駐しない）。
2. **バッチは並列可** — 別プロセス・別 `cuda:N` なら **tagger / d1 / Gemma を同時実行**してよい（例: 夜間）。
3. **設定は YAML / 環境変数**でピン。未指定時: CLIP → **`cuda:1`（3060）**。
4. llama-swap は **cuda:0（5060 Ti）** を占有しうる → d1 は **VLM 止めた隙間の cuda:0**。

---

## ワークロード別（確定案）

| ワークロード | GPU | 根拠 |
|---|---|---|
| Qwen VLM / キャプション | **cuda:0** | 最大 VRAM · 既存 llama 配置 |
| d1-3B namespace | **cuda:0** | VLM オフ時。パイロット G50 実測も 5060 Ti |
| OpenCLIP embed | **cuda:1** | Phase 1 からの既定 · 3060 12G |
| EmbeddingGemma 2 | **cuda:1** または **cuda:0** | 3060: CLIP cron と **時間帯をずらす**。5060: VLM 停止の夜 |
| cl_tagger ONNX | **cuda:2** | 2070 8G · `tagger_batch.py` |
| d1-3B namespace | **cuda:0** | 5060 Ti · `d1_batch.py`（tagger と **並列可**） |

---

## 並列バッチ例

```text
# 夜間 — VLM 止めている想定
cuda:0 (5060 Ti):  d1_batch
cuda:1 (3060):     embed_gemma2_batch   # CLIP cron 停止とセット
cuda:2 (2070S):    tagger_batch         # pixiv 36k

# 昼間 — 増分
cuda:1:  embed_pending (CLIP)
cuda:2:  tagger 増分（任意）
cuda:0:  VLM キャプション（任意）
```

**同一 GPU で避ける**: VLM + d1、CLIP + Gemma（3060 上）、d1 + Gemma。

---

## 設定

### YAML（パイロット / 本番バッチ）

```yaml
tagger:
  cuda_device_id: 2          # 2070 SUPER

embedding_gemma2:
  device: cuda:1             # 3060（夜間 Gemma のみ推奨）

d1:
  device: cuda:0             # 5060 Ti
  prefer_cuda: true
```

### 環境変数

| 変数 | 用途 | このホストの既定 |
|---|---|---|
| `SIFTIVEX_DEVICE` | OpenCLIP | **`cuda:1`**（3060） |

将来バッチ用（実装時）: `SIFTIVEX_TAGGER_CUDA_DEVICE=2`, `SIFTIVEX_D1_DEVICE=cuda:0`, `SIFTIVEX_GEMMA_DEVICE=cuda:1`

---

## ONNX cl_tagger（GPU）

1. **CPU 版を入れない** — `onnxruntime` と `onnxruntime-gpu` の併存は CPU 固定になりやすい。
2. セットアップ: `bash scripts/setup_gpu_onnx.sh`（`onnxruntime-gpu` のみ再インストール）
3. **cuDNN** — venv 内 `nvidia/cudnn/lib`。`siftivex.gpu_env.configure_nvidia_libs()` が `tagger_batch` 起動時に preload（`LD_LIBRARY_PATH` だけでは不足）。
4. **2070 SUPER（物理 GPU 2）** — `config/model_stack_pilot.yaml`:
   - `cuda_visible_devices: "2"`
   - `cuda_device_id: 0`（見えている 1 枚目として ORT に渡す）

NVML mismatch 時は `nvidia-smi` が使えなくても PyTorch / ORT CUDA は動くことがある。

---

## 実装メモ

- **hardware レポート**: `collect_hardware()` は全 GPU を列挙（パイロット JSON）。
- **ピン留め**: PyTorch `cuda:N`、ONNX `CUDAExecutionProvider` + `device_id=N`。
- **確認コマンド**（NVML 復旧後）:  
  `nvidia-smi --query-gpu=index,name,memory.total --format=csv`

---

## 関連

- [tag-stack-migration.md](../plans/tag-stack-migration.md) M5（Gemma）
- [project-roadmap.md](../plans/project-roadmap.md) §5
