# Phase 0 検証用データセット

> **参照**: [OQ-006](../../docs/open-questions.md#oq-006-phase-0-検証用データセット)

## 概要

Phase 0 の基盤検証に使う **300 枚** の画像サブセット。
元ファイルはここにコピーせず、`manifest.json` でパス参照のみ行う。

## ファイル

| ファイル | 説明 |
|---|---|
| `manifest.json` | 選定された画像のパス一覧（`scripts/select_phase0_sample.py` で生成） |
| `results/` | 検証結果（処理時間・精度メモ） |

## 選定手順

1. `config/phase0.yaml` にソースフォルダパスを設定
2. `python scripts/select_phase0_sample.py` を実行
3. 生成された `manifest.json` を目視確認

## manifest 形式

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

## 層化サンプリング

| 層 | 目標枚数 |
|---|---|
| pixiv 系 (`route/pixiv`) | 100 |
| 旧自作アーカイブ (`route/legacy`) | 100 |
| web 収集 (`route/web`) | 100 |

各層に jpg/png/webp/gif、イラスト/写真/スクショ、各種アスペクト比が混在するよう選定する。
