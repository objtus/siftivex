# Mockup Phase 2 改善（実利用検証向け）

> **目的**: React 本番前に [phase-2.md](phase-2.md) の完了条件を mockup + 実 API で試す。  
> **前提**: M1/M2 本番済（filename + tagger + d1）。

## 実装済み（2026-10-11）

| # | 項目 | 内容 |
|---|------|------|
| 1 | **索引ステータス** | Layout Lab →「索引 / タグスタック」· `GET /api/index/status` |
| 2 | **件数表示** | ヘッダ `表示 / 総数`（API 時） |
| 3 | **さらに読み込み** | 200 件ずつ `offset` 追加（API max limit） |
| 4 | 案 A | サーバ検索のみ · `include_tag` · source 別詳細 · NS/flat プレビュー |

## サムネイルが出ないとき

1. **URL**: `http://127.0.0.1:5199`（`make mockup-dev`）· **Lab → 実 API ON**（`file://` 直開き不可）
   - **`ERR_ADDRESS_IN_USE`**: 5199 が既に使用中。下記「mockup 再起動」
   - **リモート開発**（Cursor ポート転送）: 転送先 URL を使う。ローカルで二重転送すると ADDRESS_IN_USE になりやすい
   - **LAN / Tailscale から直アクセス**: `make mockup-dev MOCKUP_HOST=0.0.0.0`（ファイアウォール注意）
2. **API**: `make api-dev` が :8787 で動いている · 再起動で一覧 `has_thumbnail` 反映
3. **1 枚テスト**: グリッドで DevTools → Network → `/api/images/…/thumbnail` が **200** か **404**
4. **欠損生成**（~300 枚 under 等）:
   ```bash
   .venv/bin/python scripts/backfill_thumbnails.py
   ```
5. **原画パス**: DB `source_path` が NAS 上に存在するか（Syncthing 未同期だと生成も表示も不可）

## 試すチェックリスト

### 表示

- [ ] グリッドにサムネ（プレースホルダのみのカードは欠損 or 404）
- [ ] 詳細のプレビュー（`preview.webp` 優先）
- [ ] 詳細 **タグ（レイヤー別）**: d1 / ファイル名 / Tagger の `<details>`（一覧 API には `tag_sources` なし → 詳細 GET で表示）

### タグ検索（完了条件）

- [ ] **pixiv** · `tag:オリジナル`（filename）· Tagger チップ · `tag:種類/イラスト`
- [ ] **under** · legacy filename · `tag:"bare legs"` / チップ · d1 `tag:種類/写真`
- [ ] 空白・括弧タグ · 複数 `include_tag`（チップ複数）

### 閲覧 UX

- [ ] 3k+ ヒットで「さらに読み込み」→ スクロールしながら詳細前後
- [ ] 案 B: 探索 ⇔ 閲覧 · Esc · スクロール復元
- [ ] リスト表示 · タグプレビュー（NS │ flat）

### 自然言語

- [ ] クエリにテキストのみ（例: `青い髪`）→ CLIP スコア列

### 索引 Lab

- [ ] tagger/d1 件数が DB と一致（pixiv/under 内訳）
- [ ] 増分 ingest 後 · tagger キュー > 0 の表示

## 未着手（Phase 2 本番 UI 向け）

| 優先 | 項目 |
|------|------|
| 高 | 仮想スクロール（4 万枚ローカルソートは非現実的 → サーバページング拡張 or 上限表示の明確化） |
| 中 | FilterBar 専用 UI（source フィルタ `tagger のみ` 等） |
| 中 | 作品ページ · pixiv コンテキスト（API あり · 要磨き） |
| 低 | React 2.1 移行 · キーボード `/` フォーカス |

## 起動

```bash
make api-dev    # :8787 — コード更新後は再起動
make mockup-dev # :5199
```

Lab → 実 API ON → 索引「更新」→ pixiv/under で上記チェック。
