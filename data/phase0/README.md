# Phase 0 検証用データセット

> **参照**: [OQ-006](../../docs/open-questions.md#oq-006-phase-0-検証用データセット)

## 概要

Phase 0 の基盤検証に使う **300 枚** の画像サブセット。
元ファイルはここにコピーせず、`manifest.json` でパス参照のみ行う。

## ファイル

| ファイル | 説明 |
|---|---|
| `manifest.json` | 選定された画像のパス一覧（gitignore） |
| `results/` | 検証結果（処理時間等、gitignore） |
| `review/` | 目視評価 HTML（gitignore） |

## 選定手順

1. `config/phase0.yaml` にソースフォルダパスを設定
2. `python scripts/select_phase0_sample.py` を実行
3. 生成された `manifest.json` を目視確認

## 目視評価（タスク 0.7）

```bash
make review
# → data/phase0/review/index.html をブラウザで開く
```

- サムネイルは HTML に埋め込み（ファイル名付き画像をリポジトリに含めない）
- ファイル名は折りたたみ内に表示（ローカル確認用）
- 評価メモ欄はブラウザ内のみ（未保存）

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
