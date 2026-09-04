# REST API

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §画面, §UIパーツ

## 概要

FastAPI バックエンドが提供する REST API。フロントエンド（React）との境界定義。

## 共通

### 認証

Basic 認証（Tailscale 内限定 + アプリレベル）。

### エラーレスポンス

（TBD: 共通エラー形式）

### ページネーション

イメージリストはカーソルベースまたは offset ベース。

（TBD: 4万枚規模での方針）

---

## エンドポイント（草案）

### 検索・一覧

| Method | Path | 説明 | 状態 |
|---|---|---|---|
| GET | `/api/images` | イメージリスト取得（クエリ・ソート・ページネーション） | TBD |
| GET | `/api/images/{image_id}` | 画像詳細 | TBD |

### タグ

| Method | Path | 説明 | 状態 |
|---|---|---|---|
| GET | `/api/tags` | タグ一覧（利用頻度順/五十音順） | TBD |
| PATCH | `/api/images/{image_id}/tags` | タグ追加/削除（差分レイヤー） | TBD |
| POST | `/api/images/bulk/tags` | 一括タグ操作 | TBD |

### OCR

| Method | Path | 説明 | 状態 |
|---|---|---|---|
| PATCH | `/api/images/{image_id}/ocr` | OCR 手動上書き | TBD |
| DELETE | `/api/images/{image_id}/ocr/manual` | 自動生成に戻す | TBD |

### アルバム

| Method | Path | 説明 | 状態 |
|---|---|---|---|
| GET | `/api/albums` | アルバム一覧 | TBD |
| POST | `/api/albums` | アルバム作成 | TBD |
| POST | `/api/albums/{album_id}/members` | メンバー追加 | TBD |
| DELETE | `/api/albums/{album_id}/members` | メンバー削除 | TBD |

### 類似画像

| Method | Path | 説明 | 状態 |
|---|---|---|---|
| GET | `/api/images/{image_id}/similar` | 類似画像取得（軸指定: color/date/motif） | TBD |

### 画像配信

| Method | Path | 説明 | 状態 |
|---|---|---|---|
| GET | `/api/images/{image_id}/thumbnail` | サムネイル | TBD |
| GET | `/api/images/{image_id}/preview` | 詳細プレビュー（1000〜1500px） | TBD |
| GET | `/api/images/{image_id}/original` | 原寸 | TBD |

### インデックス管理

| Method | Path | 説明 | 状態 |
|---|---|---|---|
| POST | `/api/index/trigger` | 手動インデックス実行 | TBD |
| GET | `/api/index/status` | インデックス進捗 | TBD |

### 逆引き検索

| Method | Path | 説明 | 状態 |
|---|---|---|---|
| POST | `/api/images/{image_id}/source-search` | SauceNAO 等へのオンデマンド送信 | TBD |

---

## リクエスト/レスポンス例

（TBD: 各エンドポイントの具体例）

## 関連ドキュメント

- [query-language.md](query-language.md) — クエリパラメータの意味
- [data-model.md](data-model.md) — レスポンスに含まれるフィールド
- [ui.md](ui.md) — フロント側の API 利用箇所
