# Mockup 検索 UX 改善（案 A · 2026-10）

> **履歴**: v2 向けメモ。**現行は mockup v3（案 B）** — [mockup-design-v3.md](mockup-design-v3.md) · [ui.md](../specs/ui.md)。案 A レイアウトは `mockup/archive/v2/`。

実 API モード向けの最小変更。React 本番前の **under.iphone 試用**用。

## 変更内容

| 項目 | 内容 |
|---|---|
| 検索 | サーバ側 `q` のみ（二重フィルタ削除）· limit **200** · 件数 **表示/総数** |
| クエリ | API 時 `tagStates` をクエリから再構築（ダミー TAGS と非連動） |
| サイドタグ一覧 | API 時は説明文のみ（ダミー語彙を出さない） |
| 詳細タグ | source ごと `<details>` · EN/JA/NS の chip 色分け · 空ブロック非表示 |
| 再タグ | **非表示**（VLM legacy） |
| API 失敗 | チェックを外さずエラー表示 |

## 試すクエリ（under）

- `tag:1girl`
- `tag:種類/写真`
- `tag:制服`
- `tag:1girl tag:画角/全身`

## Phase 2 拡張

[mockup-phase2.md](mockup-phase2.md) — 索引 Lab · さらに読み込み · 実利用チェックリスト
