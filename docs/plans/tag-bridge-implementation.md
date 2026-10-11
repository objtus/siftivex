# Tag Bridge 実装計画

> **日付**: 2026-10-12  
> **仕様**: [specs/tag-bridge.md](../specs/tag-bridge.md) · **決定**: [decisions/tag-bridge.md](../decisions/tag-bridge.md)  
> **方針**: v1 は最小。localStorage ドラフト + サーバー push。不満が出たら v2（409 競合・ドラフト検索など）で対応。

## ゴール（v1 完了条件）

- [x] `data/tag_bridge.json` を正本として GET/PUT できる
- [x] `tag:制服`（bridge label）が **members の OR** で検索ヒットする（source 指定 member 対応）
- [x] mockup 設定でエントリ CRUD · 未保存 · **サーバーに保存** · 破棄 · export/import
- [x] 詳細 Tagger チップに bridge label の括弧表示（任意だが v1 推奨）
- [x] 単体テスト（手動 3 クエリは API 再起動後に確認）

## 非ゴール（v1）

- 全 tagger 語彙・Danbooru 一括 import
- ファセットの label 合算カウント
- 共起候補 UI / オフライン script
- `-tag:` の bridge 展開
- 認証・複数ユーザー
- ドラフトを push 前に検索へ反映

---

## フェーズ一覧

| フェーズ | 内容 | 依存 |
|---|---|---|
| **B0** | コアモジュール（読込・検証・パス） | — |
| **B1** | 設定 API（GET/PUT） | B0 |
| **B2** | 検索への bridge 展開（SQL OR グループ） | B0 |
| **B3** | mockup 設定 UI + localStorage + push | B1 |
| **B4** | 詳細表示ラベル + 仕上げ | B1, B3 任意 |
| **B5** | 共起候補（任意・後） | DB |

---

## B0 — コア（Python）

**新規**: `src/siftivex/tag_bridge.py`

| タスク | 詳細 |
|---|---|
| B0.1 | 定数 `DEFAULT_TAG_BRIDGE_PATH = DATA_DIR / "tag_bridge.json"`（[paths.py](../../src/siftivex/paths.py) に 1 行追加可） |
| B0.2 | `load_tag_bridge(path) -> TagBridgeDoc` — 無ければ空 entries |
| B0.3 | `validate_tag_bridge(doc) -> None \| raises ValueError` — version, label 一意, member 一意, source enum |
| B0.4 | `save_tag_bridge(path, doc)` — atomic write（temp + rename）· `updated_at` UTC |
| B0.5 | `index_by_label(doc) -> dict[str, Entry]` · `index_member_to_label(doc) -> dict[(source,tag), str]`（表示用） |
| B0.6 | `expand_include_token(token: str, doc) -> list[Member] \| None` — label ヒット時 members、否则 None |

**テスト**: `tests/test_tag_bridge.py` — validate 重複 400 相当、expand、空ファイル

---

## B1 — 設定 API

**変更**: [api/app.py](../../src/siftivex/api/app.py)

| タスク | 詳細 |
|---|---|
| B1.1 | `GET /api/settings/tag-bridge` → load |
| B1.2 | `PUT /api/settings/tag-bridge` → validate → save → 200 body |
| B1.3 | 400 JSON `{ "error": "…" }`（FastAPI HTTPException） |
| B1.4 | [api.md](../specs/api.md) に 2 エンドポイント追記 |

**キャッシュ**: v1 は **リクエスト毎にファイル read** で可。負荷が気になったら mtime メモリキャッシュ（B2 と共有）。

---

## B2 — 検索展開

**変更**: [search.py](../../src/siftivex/search.py) · [app.py](../../src/siftivex/api/app.py) `list_images`

現状の `_tag_filter_clause` は **include タグごとに AND + EXISTS（全 source）**。bridge では **1 ラベル = 1 つの OR グループ** が必要。

| タスク | 詳細 |
|---|---|
| B2.1 | `ParsedQuery` を拡張するか、内部で `list[IncludeConstraint]` に変換（`TagOnly` \| `BridgeOr(members[])`） |
| B2.2 | bridge 展開: `parse_query` + `merge_parsed_query` の各 include 文字列について `expand_include_token` |
| B2.3 | SQL: OR グループ例 — `(EXISTS … source=filename tag=制服 OR EXISTS … source=auto_tagger tag=serafuku)` |
| B2.4 | 非 bridge トークンは従来どおり（tag 文字列一致 · 全 source） |
| B2.5 | 複数 include は **グループ同士 AND** |
| B2.6 | `search_images(..., tag_bridge_path=…)` またはモジュール内 load（B1 と同パス） |

**テスト**: `tests/test_search_bridge.py`

- フィクスチャ DB + 临时 bridge JSON
- 画像 A: filename のみ 制服 · 画像 B: tagger のみ serafuku · 画像 C: 無関係
- `tag:制服`（bridge）→ A,B ヒット
- `tag:serafuku`（bridge 無し）→ B のみ
- `tag:制服` + `tag:種類/イラスト` → AND

**手動**: 既存 40k DB に example 1 エントリを PUT → mockup/curl

---

## B3 — mockup 設定 UI

**変更**: [mockup/index.html](../../mockup/index.html) · [mockup.css](../../mockup/mockup.css) · [mockup.js](../../mockup/mockup.js)

| タスク | 詳細 |
|---|---|
| B3.1 | 設定ドロワーにセクション **「タグの橋渡し」**（索引の下） |
| B3.2 | localStorage `siftivex.mockup.tagBridge.draft` — `{ version, entries, dirty, serverUpdatedAt }` |
| B3.3 | 設定を開く · API ON 時: dirty でなければ GET → draft。dirty なら「再読込しますか？」 |
| B3.4 | 一覧 UI: label · member 数 · 編集 · 削除 |
| B3.5 | 追加/編集フォーム: label + members 行（source select + tag input）· 行追加 |
| B3.6 | **サーバーに保存** → PUT body · 成功で dirty=false · 失敗メッセージ |
| B3.7 | **破棄** → GET で上書き |
| B3.8 | **JSON をエクスポート / インポート**（ファイル picker · draft に載せ dirty=true） |
| B3.9 | ヘッダまたは設定に **未保存** バッジ（dirty） |
| B3.10 | v1 UX 最小: `beforeunload` は dirty 時のみ（任意） |

**検索連携**: mockup は従来どおり `tag:ラベル` を送るだけ（**展開は API**）。push 後ユーザーが再検索 or 自動 `refreshList()` 1 回（任意・実装時判断）。

**API OFF**: セクションに「接続時のみサーバー保存と検索反映」· export/import のみ。

---

## B4 — 詳細表示（推奨）

| タスク | 詳細 |
|---|---|
| B4.1 | API 接続後に bridge を 1 回 GET（または index status と同タイミング）· `member → label` マップを保持 |
| B4.2 | `renderDetailTags` の Tagger チップ: `(source,tag)` が bridge にあれば `tag（label）` |
| B4.3 | push 成功後に bridge キャッシュ再 GET |

**後回し可**: ファセットに bridge label 行（B5 以降）

---

## B5 — 半自動候補（任意）

| タスク | 詳細 |
|---|---|
| B5.1 | `scripts/suggest_tag_bridge.py` — filename × auto_tagger 共起 Top N（ルート・min_count 引数） |
| B5.2 | 設定 UI「候補を読込」（JSON ファイル or 将来 GET）· 1 行採用 → draft に append |

---

## 実装順（推奨スプリント）

```
Week A（バックエンド）
  B0 → B1 → B2 + tests
  → curl で PUT example + GET search 確認

Week B（UI）
  B3（設定 CRUD + push）
  B4（詳細括弧）
  → mockup 手動: 追加 → push → tag:ラベル でヒット

Week C（任意）
  B5 共起 script
  docs/api.md · mockup-phase2 に bridge 1 行
```

並行不可: **B2 完了前に mockup だけ実装しても検索は効かない**。

---

## ファイル変更予測

| パス | 操作 |
|---|---|
| `src/siftivex/tag_bridge.py` | 新規 |
| `src/siftivex/paths.py` | 定数 |
| `src/siftivex/search.py` | OR グループ |
| `src/siftivex/api/app.py` | GET/PUT + search に bridge 渡し |
| `tests/test_tag_bridge.py` | 新規 |
| `tests/test_search_bridge.py` | 新規 |
| `mockup/index.html` | 設定 UI |
| `mockup/mockup.css` | 橋渡しフォーム |
| `mockup/mockup.js` | draft / push / 表示 |
| `docs/specs/api.md` | エンドポイント |
| `scripts/mockup_phase2_verify.py` | 将来: bridge 1 エントリ E2E（任意） |

---

## リスクと v2 バックログ

| リスク | v1 | v2 で検討 |
|---|---|---|
| 未 push で検索に効かない | 許容 · push 後に再検索 | ドラフトを検索 API に一時送信 |
| 多端末上書き | last-write-wins | PUT + `updated_at` 409 |
| 複数タブ localStorage | 許容 | storage イベント |
| bridge 変更の即反映 | PUT 後 file read | mtime キャッシュ無効化 |

---

## 関連リンク

- [project-roadmap.md](project-roadmap.md) — 次の作業候補
- [tag-stack-migration.md](tag-stack-migration.md) — M4 `inferred_ja`（bridge member に追加可能）
