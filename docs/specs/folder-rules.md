# フォルダルール・取り込みプロファイル

> **状態**: スケルトン
> **参照**: [blueprint.md](../../blueprint.md) §取り込みルート・フォルダルール

## 概要

フォルダパス単位の取り込みルール。自動付与タグとファイル名パーサーを定義する。
設定は YAML ファイルに保持し、GUI はそのフォーム、エージェントも同ファイルを読み書きする。

## 設定ファイル

| ファイル | 内容 |
|---|---|
| `folder_rules.yaml` | フォルダパス → プロファイルのマッピング |
| `parsers/` | パーサー定義（正規表現 + 名前付きキャプチャ） |

（TBD: ファイル配置場所、スキーマ）

## プロファイル構造（草案）

```yaml
# folder_rules.yaml（草案）
profiles:
  pixiv_default:
    route_tag: route/pixiv
    parser: pixiv_downloader_v1
    fixed_tags: []

  legacy_archive:
    route_tag: route/legacy
    parser: legacy_archive_v1
    fixed_tags: []

rules:
  - path_prefix: /path/to/pixiv/
    profile: pixiv_default
  - path_prefix: /path/to/legacy/
    profile: legacy_archive
```

## パーサー定義

### pixiv ダウンローダー形式

（TBD: 正規表現 → [OQ-002](../open-questions.md)）

```yaml
# parsers/pixiv_downloader_v1.yaml（草案）
name: pixiv_downloader_v1
pattern: "TBD"
captures:
  artist: ...
  work_id: ...
  date: ...
  pixiv_tags: ...
```

### 旧自作アーカイブ形式

（TBD: 正規表現 → [OQ-003](../open-questions.md)）

### web 収集（パーサーなし）

`route/web` タグのみ自動付与。ファイル名からのメタデータ抽出なし。

## パスマッチング

- フォルダパス前方一致（孫フォルダ以下も含む）
- より具体的なルールが優先（最長一致）

（TBD: 競合時の挙動）

## 関連ドキュメント

- [tags.md](tags.md) — route タグの定義
- [indexing.md](indexing.md) — 取り込み時の適用タイミング
- [data-model.md](data-model.md) — 抽出メタデータの保存先
