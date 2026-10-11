# Mockup Phase 2 検証結果

> **日付**: 2026-10-12（Phase 2 クローズ追記あり）  
> **方法**: `uv run --with playwright python scripts/mockup_phase2_verify.py`（API 直 + mockup :5199）  
> **環境**: サーバー上 headless · ブラウザ実機は別途体感確認推奨

## サマリー

| 区分 | 結果 |
|---|---|
| API タグ/CLIP 検索 | ✅ 代表クエリすべてヒット |
| mockup UI 自動 | ✅ 30/30（`scripts/mockup_phase2_verify.py` exit 0） |
| 修正した UX | 自然言語検索時に **並びを関連度へ自動切替**（`mockup.js`） |

## チェックリスト対応

### 表示

- [x] グリッドサムネ（先頭 40 枚で 30+ 成功 · 自動）
- [x] 詳細プレビュー（API `has_preview` 画像で 200 · 自動）
- [x] 詳細タグ（構造化 / ファイル名/pixiv / Tagger · 自動）

### タグ検索

- [x] `tag:オリジナル` · `tag:種類/イラスト` · `tag:"bare legs"` · `tag:種類/写真` · `tag:1girl`（API）
- [x] ファセットクリック · Shift 除外 · すべて解除（UI 自動）
- [ ] **手動**: pixiv / under **ルートを切り替え**たうえでの同種クエリ（ルート ID は `route/pixiv` · `route/under-iphone`）

### 閲覧 UX

- [x] 27k ヒットで 200→400 枚ロード（無限スクロール · 自動）
- [x] 一覧へ戻る · アクティブカード一致（自動）
- [~] スクロール位置復元 — 自動では 1200px 設定に対し ~170px 程度に留まることがあり。**実機で「一覧へ」後の位置**を確認推奨
- [x] 複数ページ作品 · `]` · strip 同期（自動）

### 自然言語

- [x] `青い髪` → CLIP score · 表のスコア列 · 関連度ソート（自動 + 修正済）

### 設定 · 索引

- [x] 索引パネルと DB 件数（40,305 / 40,320 · 自動）
- [x] テーマ localStorage（自動）

## 手動でまだ見るとよいもの

1. **スマホ幅**（フィルタドロワー · スワイプ · 情報トグル）— SSH 経由のブラウザで DevTools デバイスモード
2. **高速ホイール**で詳細送り — 以前の安定化が実機でも問題ないか
3. ~~**資料探し 15 分**~~ — 2026-10-12 試用 · 現状満足 · Phase 2 クローズ

## 再実行

```bash
make api-dev    # :8787
make mockup-dev # :5199
uv run --with playwright python scripts/mockup_phase2_verify.py
```

終了コード 0 なら自動項はすべて OK。
