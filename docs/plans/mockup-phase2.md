# Mockup Phase 2（v3）— 実利用検証

> **目的**: React 本番前に [phase-2.md](phase-2.md) の完了条件を **mockup v3 + 実 API** で試す。  
> **UI 契約**: [ui.md](../specs/ui.md) · [mockup-design-v3.md](mockup-design-v3.md)  
> **前提**: M0〜M2 本番済（40,305 枚に filename + tagger + d1）。

## 参照実装

| パス | 内容 |
|---|---|
| `mockup/index.html` | シェル（topbar / sidebar / list / viewer / settings） |
| `mockup/mockup.css` | トークン・ダーク/ライト・レスポンシブ |
| `mockup/mockup.js` | 状態・API・レイアウト・詳細パイプライン |
| `mockup/archive/v2/` | 旧 Layout Lab 版（比較用） |

## 実装済み（v3 · 2026-10-12）

| 項目 | 内容 |
|---|---|
| 探索 ⇔ 閲覧 | 案 B（`mode-explore` / `mode-view`）· 戻る · Esc · `history.pushState` |
| 左サイドバー | ルート · 絞り込みチップ · 結果内タグファセット（件数バー） |
| 一覧 | 行揃え / Masonry / 正方形 / 表 · サムネサイズ · 200 件ページング + 無限スクロール |
| 詳細 | 作品メタ · ページ strip · **source 別タグ** · ファイル情報 |
| 設定 | テーマ · API 接続 · `GET /api/index/status` 索引状況 · キー一覧 |
| モバイル | ≤1099px フィルタドロワー · ≤899px 縦積み + 情報トグル · スワイプ |
| 安定化 | サムネ同時読み込み制限 · 詳細 race ガード · 画像プリロード挿入 |

**廃止（v2 から）**: Layout Lab · 案 A · 一括選択 · 再タグ · 仮の類似画像。

## 起動

```bash
make api-dev      # :8787 — 更新後は再起動
make mockup-dev   # :5199
```

1. `http://127.0.0.1:5199/` を開く（`file://` 不可）
2. API 起動中なら自動接続。オフのときは **設定 → API に接続する**
3. **設定 → 索引の状況 → 更新** で tagger/d1 件数を確認

### リモート開発（Cursor + SSH）

- ブラウザは **メイン PC** · 転送 URL（例: `http://127.0.0.1:5199/`）を使用
- `ERR_ADDRESS_IN_USE`: 5199 の二重起動 · `ps` で `mockup_server` を確認して再起動

### LAN / Tailscale

`make mockup-dev MOCKUP_HOST=0.0.0.0`（ファイアウォール注意）

## サムネイルが出ないとき

1. Network で `/api/images/…/thumbnail` が **200** か **404**
2. `make api-dev` 稼働 · 一覧の `has_thumbnail`
3. 欠損生成: `.venv/bin/python scripts/backfill_thumbnails.py`
4. DB `source_path` が NAS 上に存在するか（Syncthing 未同期だと不可）

## 自動検証

```bash
make api-dev && make mockup-dev   # 別ターミナル
uv run --with playwright python scripts/mockup_phase2_verify.py
```

結果: [mockup-phase2-results.md](mockup-phase2-results.md)（2026-10-12 · 30 項目共に OK）。

## 試すチェックリスト

### 表示

- [x] グリッドにサムネ — 自動 ✅
- [x] 詳細プレビュー — 自動 ✅
- [x] 詳細タグ（source 別）— 自動 ✅

### タグ検索（Phase 2 完了条件）

- [x] API: `tag:オリジナル` · `tag:種類/イラスト` · `tag:"bare legs"` · `tag:1girl` — 自動 ✅
- [ ] **手動**: サイドバーで **pixiv / under** を選んで同種クエリ
- [x] ファセット / 除外 / 解除 — 自動 ✅

### 閲覧 UX

- [x] 2.7k+ ヒットで追加ロード — 自動 ✅
- [~] 一覧へ戻る · スクロール位置 — 選択カード ✅ · スクロールは実機確認
- [x] 複数ページ · `[` `]` · strip — 自動 ✅

### 自然言語

- [x] `青い髪` → 関連度 + 表スコア — 自動 ✅（NL 時は関連度へ自動切替）

### 設定 · 索引

- [x] tagger/d1 件数 — 自動 ✅
- [x] テーマ保持 — 自動 ✅

### 手動のみ推奨

- [ ] タブレット / スマホ（ドロワー · スワイプ · 情報）
- [x] **15 分の資料探し** — 2026-10-12 · 満足 · Phase 2 クローズ

## 未着手（Phase 2 本番 UI 向け）

| 優先 | 項目 |
|---|---|
| 高 | 大規模一覧方針（仮想スクロール or サーバページングの明文化 · 4 万枚をクライアント保持しない） |
| 中 | source 限定フィルタ（例: Tagger のみ） |
| 中 | 作品コンテキスト API の edge case 磨き |
| 低 | React 2.1 移行（mockup v3 を写す） |

## 関連

- [phase-2.md](phase-2.md) — 完了条件
- [tag-stack-migration.md](tag-stack-migration.md) — 検証チェックリスト
