# モデルスタック評価 — 総括

> **日付**: 2026-10-10  
> **コーパス**: Phase 0 manifest 300（under.iphone）· RTX 5060 Ti  
> **詳細ログ**: [model-stack-pilot-memo.md](model-stack-pilot-memo.md)

## 結論（短く）

| コンポーネント | Go | 役割 |
|---|---|---|
| **cl_tagger** | **Yes** | 全件の **英語 booru 密度タグ**（`source=auto_tagger` 想定） |
| **filename** | **維持** | 取り込み前の **日本語確定タグ**（変更しない） |
| **d1-3B** | **Yes** | **namespace 5 軸**の choice 確定（タグ生成しない） |
| **EmbeddingGemma 2** | **試行継続** | CLIP 代替より **英語 booru + 日本語 filename 横断検索**の検証が次 |
| **VLM (Qwen VL)** | **スパース** | 主タグ源から外す。キャプション・例外のみ（V10 は server 未起動で未計測） |

---

## Tagger と filename の考え方（重要）

**別語彙・別役割で共存**する。統合して 1 リストに潰さない。

| レイヤ | 語彙 | 由来 | 用途 |
|---|---|---|---|
| **filename** | 日本語（`毛`, `制服`, …） | 人間がファイル名に付けた確定情報 | UI・日本語検索・コレクション固有の軸 |
| **auto_tagger** | 英語 booru（`1girl`, `school uniform`, …） | cl_tagger ONNX | 属性の網羅・外部タグ体系・英語クエリ |
| **d1 → namespace** | 日本語 `種類/` `画角/` … | 閉じた choice | フィルタ・統計・VLM namespace の置換 |
| **VLM auto** | （レガシー） | 汎用 LLM | 新規付与は止め、既存は参照のみ |

- **Jaccard(tagger top, VLM auto) ≈ 0.003** は失敗ではなく **意図した非重複**。検索は **両方 FTS / ベクトル**に載せる。
- **エイリアス辞書**（将来）: 高頻度の英日対（`school uniform` ↔ `制服`）は **検索ブリッジ**用。tagger 出力を filename に上書きしない。

### cl_tagger 実測

- M300: **299 枚 / 532s**（~**1.78 s/枚**）· 閾値 general 0.35 / character 0.85
- 内容: `1girl`, `photo (medium)`, `realistic`, `highres` 等 — **数も内容も実用**（ユーザー目視と一致）
- 分析: `pilot_tagger_analysis_m300.json` · 目視: `data/phase0/review/pilot_g30_review.html`

---

## d1-3B

- G50 GPU: **50 枚 / 24s**（~**0.48 s/枚**）· 種類/ **98%** · 画角/ 58% · アングル/ 60% · 人数/ 67%（弱正解 = VLM namespace）
- **Ablation**（`pilot_d1_ablation_g50.json`）— 軸別 accuracy:

| モード | 人数/ | 画角/ | アングル/ | 種類/ |
|---|---:|---:|---:|---:|
| 画像のみ | 0.673 | 0.58 | 0.60 | 0.98 |
| + tagger hints | **0.735** | **0.62** | 0.58 | 0.98 |
| + filename hints | **0.735** | 0.58 | 0.58 | 0.98 |

→ **人数・画角**は tagger 英語ヒントがわずかに効く。**filename 日本語**は人数では同等だが画角は tagger より劣る。運用: **d1 state には tagger top-N を載せ、filename は別途 UI 確定**がよさそう。

---

## EmbeddingGemma 2

- M300: **296 枚 / 35.7s**（~**0.12 s/枚**）· GPU bf16
- 検索プローブ 80 枚: `pilot_search_compare.json` — 実写コーパスでは CLIP/Gemma Top5 が似る。`school uniform` / `制服` 系は **Gemma が filename 寄りファイル名にヒット**しやすい傾向（要 G30 目視で勝敗記録）
- **移行**: CLIP 4 万埋め込み済み → Gemma は **M5 · 別テーブル/`model` 列**。3 GPU なら **tagger/d1 と別 `cuda:N` で並列再 embed**可 → [gpu-workloads.md](../setup/gpu-workloads.md)

---

## 併用像（10 例）

機械抽出: [pilot_integration_stories.json](pilot_integration_stories.json)

```
filename (JA)  →  UI・日本語 tag: 検索
     ↓
tagger (EN)    →  auto_tagger: 密度・英語検索・embed クエリ
     ↓
d1 (choice)    →  種類/画角/… を namespace タグとして保存
     ↓
embed          →  Gemma2(画像)+ クエリ(EN/JA) で類似
```

例: `IMG0272_パンツ.JPG` — filename `パンツ` · tagger `underwear, panties, 1girl` · embed クエリ例 `underwear, panties`

---

## レガシー VLM

- V10 計測: **2026-10-10 llama-server :8081 未応答** → `model_stack_pilot_vlm_v10.json` は未生成 or 全 fail
- 方針: **`source=auto`（VLM タグ）を廃止** — 既存行は [tag-stack-migration.md](tag-stack-migration.md) M0 で削除。VLM は [vlm-on-demand.md](../decisions/vlm-on-demand.md) で **キャプションのみ**。

---

## ADR

- [role-based-model-stack.md](../decisions/role-based-model-stack.md): 実測を反映済み。**accepted** は実装 PR（`auto_tagger` source・ワーカー）後でも可。

## 今後の進め方

1. **[tag-stack-migration.md](tag-stack-migration.md)** — M0 purge → M1 tagger → M2 d1 → M3 API  
2. [model-stack-rollout.md](model-stack-rollout.md) — フェーズ C 以降（JA master / inferred_ja）  
3. [project-roadmap.md](project-roadmap.md) — Phase 2 との順序
