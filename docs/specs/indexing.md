# インデックスパイプライン

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §自動インデックス化フロー, §4万枚の処理方針

## 概要

新規画像の検知から DB/LanceDB への書き込みまでの処理フロー。
n8n（トリガー・スケジュール）+ FastAPI/スクリプト（処理本体）+ SQLite キュー（VLM ジョブ管理）。

## フロー

```
フォルダ監視(n8n トリガー)
  │
  ├─ [即時処理]
  │    ├─ content_hash 計算 (BLAKE3)
  │    ├─ サムネイル生成 (libvips)
  │    ├─ CLIP embedding 生成 → LanceDB 書き込み
  │    ├─ OCR 実行 → auto_ocr 書き込み
  │    └─ route タグ付与 (folder-rules 参照)
  │
  └─ [キュー投入]
       └─ VLM タグ付けジョブ → pending キュー
            └─ (夜間バッチ等) VLM 実行 → auto_tags 更新
```

## 処理詳細

### content_hash

（TBD: BLAKE3 計算タイミング、重複検出時の挙動）

### サムネイル

3段階:

| サイズ | 用途 | 生成タイミング |
|---|---|---|
| サムネイル（極小） | グリッド一覧 | 取り込み時 |
| 詳細プレビュー（1000〜1500px） | 詳細画面 | 取り込み時 |
| 原寸 | ズーム時 | オンデマンド |

（TBD: 具体的なピクセルサイズ・フォーマット）

### CLIP embedding

（TBD: モデル選定、GPU 配置、GIF の代表フレーム抽出）

### OCR

（TBD: PaddleOCR / manga-ocr の使い分け条件）

### VLM タグ付け

（TBD: llama-swap 経由の呼び出し、プロンプト → [tags.md](tags.md)）

## キュー管理

SQLite 上の簡易キューテーブル + n8n スケジュール実行。

（TBD: テーブル定義、リトライ、失敗時の扱い）

## 再インデックス

| トリガー | 対象 | 動作 |
|---|---|---|
| 手動（UI/API） | 指定画像 | auto_tags 上書き（manual 保護） |
| 一括再タグ付け | 選択画像群 | 同上 |
| 定期スキャン | 監視フォルダ全体 | 新規/移動/missing 検出 |

## ファイル消失・移動の検出

（TBD: blueprint §移動・削除されたファイルの検出 の具体化）

## 関連ドキュメント

- [data-model.md](data-model.md) — 書き込み先テーブル
- [tags.md](tags.md) — VLM プロンプト
- [folder-rules.md](folder-rules.md) — route タグ・パーサー
