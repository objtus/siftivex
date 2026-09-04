# 未決定事項

> blueprint.md の「未決定・今後の検討事項」を実装向けに管理する。
> 解決した項目は該当 spec に反映し、ここからは削除または「解決済み」セクションへ移す。

## 凡例

| ステータス | 意味 |
|---|---|
| `open` | 未着手 |
| `discussing` | 検討中 |
| `blocked` | 他の決定待ち |
| `resolved` | 解決済み（spec に反映済み） |

| 優先度 | 意味 |
|---|---|
| P0 | Phase 0 着手前に必要 |
| P1 | Phase 1 着手前に必要 |
| P2 | Phase 2 以降で可 |
| P3 | 後回し可 |

---

## オープン

| ID | 項目 | 優先度 | ステータス | ブロックする Phase | 関連 spec |
|---|---|---|---|---|---|
| OQ-001 | 身体部位名前空間の具体的リスト | P2 | discussing | Phase 2 以降可 | [tags.md](specs/tags.md) |
| — | 雑多なウェブ収集アーカイブ（~30–40k）の同期・取り込み | P2 | open | Phase 2+ | [paths.yaml.example](../config/paths.yaml.example) `web_misc` |

---

## 解決済み

### OQ-009: Phase 1 初回投入の範囲と順序

- **決定日**: 2026-09-04
- **状態**: resolved
- **反映先**: [phase-1-prep.md](decisions/phase-1-prep.md), [indexing.md](specs/indexing.md)

**決定: B** — under.iphone + pixiv の両方を Phase 1 初回投入対象（合計 ~40,554 枚）。

実行順: under.iphone（~4k、検証）→ pixiv（~36.5k、bulk）。

---

### OQ-010: `image_metadata` を Phase 1 で作るか

- **決定日**: 2026-09-04
- **状態**: resolved
- **反映先**: [data-model.md](specs/data-model.md), [folder-rules.md](specs/folder-rules.md)

**決定: C** — テーブル作成 + pixiv ingest 時に sidecar / パーサーから書き込み。

---

### OQ-005: `image_id` の生成規則

- **決定日**: 2026-09-04
- **状態**: resolved
- **反映先**: [data-model.md](specs/data-model.md) §識別子

**決定内容**

| フィールド | 形式 | 例 |
|---|---|---|
| `content_hash` | BLAKE3-256 の hex 全文（64 文字） | `a1b2c3d4…`（64 chars） |
| `image_id` | `img_` + `content_hash` の先頭 16 文字 | `img_a1b2c3d4e5f67890` |

**理由**

- blueprint の「ハッシュを主キー相当として扱う」方針に沿い、同一ファイル内容は常に同じ ID になる（deterministic）
- ファイル移動・再取り込み時に `content_hash` UNIQUE 制約で重複検出、`source_path` のみ更新
- `img_` プレフィックスによりクエリトークン（`similar_to:img_xxxx`）と他の識別子を区別可能
- 16 hex 文字（64 bit）で 4 万枚規模では衝突リスクは実質無視できる。衝突時は `content_hash` 全文で解決

**生成手順**

```
1. ファイルバイト列を BLAKE3 でハッシュ
2. content_hash = hexdigest()           # 64 文字
3. image_id     = "img_" + content_hash[:16]
4. INSERT … ON CONFLICT(content_hash) DO UPDATE SET source_path = …
```

---

### OQ-006: Phase 0 検証用データセット

- **決定日**: 2026-09-04
- **状態**: resolved
- **反映先**: [phase-0.md](plans/phase-0.md), [data/phase0/README.md](../data/phase0/README.md)

**決定内容**

| 項目 | 方針 |
|---|---|
| 枚数 | **300 枚**（数百枚の中央値。±50 は許容） |
| 選定方法 | 層化サンプリング（下記） |
| 保存方式 | **元ファイルはコピーしない**。manifest でパス参照のみ |
| 保存場所 | リポジトリ内 `data/phase0/`（gitignore 対象） |
| 設定 | `config/phase0.yaml` にソースフォルダパスを記載 |

**更新 (2026-09-04)**: under.iphone + pixiv とも同期済。pixiv は `.../pixiv`（~36,560 枚）。

| 層 | 目標枚数 | 備考 | 状態 |
|---|---|---|---|
| under.iphone | 300（Phase 0）/ 3,994（全体） | Phase 0 サンプル | 同期済 |
| pixiv | 100（Phase 0 予定）/ 36,560（全体） | Phase 1 bulk 対象 | 同期済 |
| iCloud Photos | — | 後回し | 未同期 |

→ 同期手順: [setup/windows-sync.md](setup/windows-sync.md)

各層内で以下のバリエーションを意図的に含める:

- 形式: jpg / png / webp を中心に、gif を 5〜10 枚
- 種類: イラスト・写真・スクショ・資料が混在
- アスペクト比: 横長・縦長・正方形が混在

**manifest 形式** (`data/phase0/manifest.json`)

```json
{
  "version": 1,
  "created_at": "2026-09-04T00:00:00+09:00",
  "entries": [
    {
      "source_path": "/absolute/path/to/image.jpg",
      "route_tag": "route/pixiv",
      "note": ""
    }
  ]
}
```

**選定スクリプト**

Phase 0 タスク 0.1 で `scripts/select_phase0_sample.py` を作成し、`config/phase0.yaml` のソースパスから manifest を生成する。

---

### OQ-003: 旧自作アーカイブ（under.iphone）ファイル名パーサー

- **決定日**: 2026-09-04
- **状態**: resolved
- **反映先**: [folder-rules.md](specs/folder-rules.md), `config/parsers/under_iphone_legacy_v1.yaml`

形式 `{id}_{tag}-{tag}.ext`。実装: `src/siftivex/filename_tags.py`。

---

### OQ-004: 未分類 / 要再タグ

- **決定日**: 2026-09-04
- **状態**: resolved
- **反映先**: [tags.md](specs/tags.md), [phase-1-prep.md](decisions/phase-1-prep.md)

| タグ | 条件 |
|---|---|
| `未分類` | VLM 成功だが namespace + flat が空 |
| `要再タグ` | VLM 失敗。`--retry-errors` で再実行 |

---

### OQ-007: タグのエイリアス辞書

- **決定日**: 2026-09-04
- **状態**: resolved

`config/tag_vocabulary.yaml` の `aliases` で運用。

---

### OQ-008: OCR ハイブリッド

- **決定日**: 2026-09-04
- **状態**: resolved
- **反映先**: [indexing.md](specs/indexing.md), [phase-1-prep.md](decisions/phase-1-prep.md)

ingest: dedicated OCR（プロファイルで manga-ocr / PaddleOCR）。VLM: `ocr_text`。マージ: dedicated 優先。

---

### OQ-002: pixiv ファイル名パーサー / sidecar

- **決定日**: 2026-09-04
- **状態**: resolved
- **反映先**: [folder-rules.md](specs/folder-rules.md), `src/siftivex/pixiv_filename.py`

**決定内容**

| 優先 | ソース | 対象 |
|---|---|---|
| 1 | `{stem}.pixiv.json` sidecar | 短名移行後 ~8,118 件 |
| 2 | `parse_pixiv_filename()` | 旧 `date_*` 形式 ~28,451 件 |
| 3 | なし | `route/pixiv` のみ |

形式バリアント: `_tags_` あり/なし、`id_` / `_` work_id 区切り。実装済みテスト: `tests/test_pixiv_filename.py`
