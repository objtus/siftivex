# タグスタック移行計画（VLM auto 廃止 → filename + tagger + d1）

> **日付**: 2026-10-10  
> **状態**: **計画確定** — 実装は本ドキュメントの順に進める  
> **関連**: [project-roadmap.md](project-roadmap.md), [model-stack-rollout.md](model-stack-rollout.md), [model-stack-pilot-findings.md](model-stack-pilot-findings.md)

## 決定

1. **既存 VLM タグ（`source='auto'`）は一括削除してよい。** タグ方針を最初から組み直す。
2. **触らない**: `filename`, `manual_added`, `manual_removed`, CLIP embed / LanceDB。
3. **`vlm_caption`**: 列は残す。キャプションだけ必要なら後から VLM スパースで再生成。タグとは分離。
4. **pixiv ~36k の pending VLM ジョブ**は破棄。代わりに **tagger バッチ**。
5. **新規 ingest** では VLM キューに積まない（実装後）。tagger / d1 キュー（またはバッチ）に切替。

### タグの正（2026-10 以降）

| 役割 | source | 備考 |
|---|---|---|
| 日本語確定 | `filename` | パーサー / pixiv sidecar |
| 英語 booru | `auto_tagger` | cl_tagger 全件 |
| namespace 5 軸 | `auto_d1` | d1 choice |
| 推定 flat JA | `inferred_ja` | d1 + master 語彙（後続） |
| VLM レガシー | ~~`auto`~~ | **削除。新規付与なし** |
| キャプション | `images.vlm_caption` | オンデマンドのみ |

検索・UI は **source をマージせず並列表示**（[tags.md](../specs/tags.md)）。

---

## 現状スナップショット（移行前）

| 項目 | 概算 |
|---|---|
| `image_tags` `auto` 行数 | ~145k |
| VLM タグ付き画像 | ~3,926（under.iphone） |
| `filename` 行数 | ~273k |
| `index_jobs` `vlm_tag` pending | ~36,413（pixiv） |

---

## 実施フェーズ

### M0 — クリーンアップ（実装前でも SQL 可）

| # | 作業 | 完了条件 |
|---|---|---|
| M0.1 | `data/siftivex.db` バックアップ | ファイルコピー |
| M0.2 | `DELETE FROM image_tags WHERE source='auto'` | auto 行 0 |
| M0.3 | pending `vlm_tag` を cancel/delete | pending 0 |
| M0.4 | （任意）`要再タグ` が filename/manual に残っていれば整理 | 検索ノイズなし |
| M0.5 | スクリプト化 `scripts/purge_vlm_auto_tags.py`（dry-run 付き） | ✅ `scripts/purge_vlm_auto_tags.py` |

**注意**: `effective_tags` / FTS は現状 `auto` を含む。M0 後は **filename 中心**に一時的に戻る。M1 完了まで英語タグ検索は弱い。

### M1 — Tagger 本番（Rollout A）

| # | 作業 | 完了条件 |
|---|---|---|
| M1.1 | `replace_tags(..., "auto_tagger", ...)` + pilot `tagger_cl` 再利用 | 単体テスト |
| M1.2 | `tagger_batch.py` / `n8n_task.py tagger` | ✅ `scripts/tagger_batch.py` · `n8n_task.py tagger` |
| M1.3 | under.iphone **~500 枚**試行 → API 詳細・検索 | `auto_tagger` 表示 |
| M1.4 | pixiv 全件バッチ（夜間） | 36k に tagger 付与 |
| M1.5 | ingest 増分で tagger ジョブ enqueue | cron 文書化 |

### M2 — d1 namespace（Rollout B）

| # | 作業 | 完了条件 |
|---|---|---|
| M2.1 | `auto_d1` 保存、5 軸質問セット | ✅ `scripts/d1_batch.py` · `replace_auto_d1_namespace` |
| M2.2 | filename タグを d1 state（tagger は渡さない） | ✅ `filename_hint_state` |
| M2.3 | under.iphone 試行 → 全ルート拡大 | `d1_batch --route …`（**auto_tagger 済み**から） |

### M3 — 検索・API・UI（Rollout D の一部）

| # | 作業 | 完了条件 |
|---|---|---|
| M3.1 | `search.py` / FTS: `auto_tagger`, `auto_d1`, `inferred_ja` | タグ検索 |
| M3.2 | API `tag_sources` 拡張（mockup 同期） | 詳細 JSON |
| M3.3 | Phase 2.9 バッチ進捗 API/UI | ✅ `GET /api/index/status` → `tag_stack`, `tag_stack_by_route` |

### M4 — 日本語推定（Rollout C）

master 集計 → 編集 → d1 → `inferred_ja`。M1/M2 安定後。

### M5 — α

| 項目 | 内容 |
|---|---|
| CLIP | 維持（`cuda:1` · 増分 cron） |
| EmbeddingGemma 2 | 全件再 embed 可。**ロードマップ上は M5**。[gpu-workloads.md](../setup/gpu-workloads.md) — **3 GPU 並列**（例: tagger@2 + Gemma@1 + d1@0） |
| VLM | [vlm-on-demand.md](../decisions/vlm-on-demand.md) — **キャプション・例外**（通常 `cuda:0` / llama-swap） |

VRAM は **1 枚前提にしない**。夜間バッチは GPU を役割分担して同時走行してよい。

---

## ingest の目標フロー（M1 以降）

```
ingest → filename + サムネ + OCR + index_jobs(tagger) [+ d1]
embed  → CLIP（現行）
tagger → auto_tagger（バッチ / cron）
d1     → auto_d1（tagger 後）
VLM    → 手動のみ（caption、任意）
```

`indexing.md` の VLM セクションは **レガシー運用**として残し、目標フローを先頭に追記済みとする。

---

## ドキュメント更新（本計画と同時）

| ファイル | 内容 |
|---|---|
| [project-roadmap.md](project-roadmap.md) | 現在地・次アクション |
| [model-stack-rollout.md](model-stack-rollout.md) | M0 前置 |
| [indexing.md](../specs/indexing.md) | 目標パイプライン |
| [tags.md](../specs/tags.md) | source 確定・`auto` 廃止 |
| [phase-2.md](phase-2.md) | 完了条件・優先順 |
| [role-based-model-stack.md](../decisions/role-based-model-stack.md) | パイロット後の確定事項 |

---

## 実装後の検証チェックリスト

- [ ] 詳細: filename / auto_tagger / auto_d1 が分離表示
- [ ] タグ検索: `1girl`（EN）と `制服`（JA filename）の両方
- [ ] pixiv 画像: filename + auto_tagger（VLM なし）
- [ ] VLM retag API: **caption のみ** or 明示的レガシモード（タグ上書きしない）
- [ ] cron: VLM 常時実行なし
