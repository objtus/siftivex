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
| OQ-001 | 身体部位名前空間の具体的リスト | P1 | open | Phase 0（VLM 検証）, Phase 1 | [tags.md](specs/tags.md) |
| OQ-002 | ファイル名パーサーの正規表現（pixiv ダウンローダー形式） | P1 | open | Phase 1 | [folder-rules.md](specs/folder-rules.md) |
| OQ-003 | ファイル名パーサーの正規表現（旧自作アーカイブ形式） | P1 | open | Phase 1 | [folder-rules.md](specs/folder-rules.md) |
| OQ-004 | 未分類判定の定義（「タグが確定しなかった」の条件） | P1 | open | Phase 0（VLM 検証） | [tags.md](specs/tags.md) |
| OQ-007 | タグのエイリアス辞書の要否 | P3 | open | — | [tags.md](specs/tags.md) |

---

## 解決済み

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

**更新 (2026-09-04)**: 最初は **under.iphone のみ**（Syncthing 同期後）。pixiv / iCloud は後続。

| 層 | 目標枚数 | パス（サーバー） | 状態 |
|---|---|---|---|
| under.iphone | 300 | `/home/objtus/Sync/siftivex-archive/under.iphone` | **先行** |
| pixiv ブクマ | 100 | `/home/objtus/Sync/siftivex-archive/pixiv-bookmarks` | 後続 |
| iCloud Photos | — | `/home/objtus/Sync/siftivex-archive/icloud-photos` | 後回し |

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
