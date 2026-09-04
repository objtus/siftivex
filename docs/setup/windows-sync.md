# Windows ↔ サーバー 画像同期

> **参照**: [blueprint.md](../../blueprint.md) §推奨技術スタック（Syncthing）

## 方針

- 元画像は **Windows / NAS 上が正本**。サーバーへ Syncthing で同期
- DB・embedding・LanceDB は **サーバー上のみ**（同期しない）
- 実際のフォルダパスは **`config/paths.yaml`**（gitignore）に記載。テンプレートは [paths.yaml.example](../../config/paths.yaml.example)

## パス対応表

| 名前 | Windows 側（正本） | サーバー側（同期先） | route タグ | 備考 |
| --- | --- | --- | --- | --- |
| under.iphone | `paths.yaml` → `archives.under_iphone` | 同上 | `route/under-iphone` | Phase 0 対象 |
| pixiv ブクマ | 同上 → `archives.pixiv_bookmarks` | 同上 | `route/pixiv` | 後続 |
| iCloud Photos | 同上 → `archives.icloud_photos` | 同上 | `route/icloud` | 後回し（容量大） |

---

## Step 1: under.iphone（NAS → サーバー）

### 1-A. Windows: NAS をドライブレターに割り当て

Syncthing は UNC パス（`\\server\share`）を直接監視できない場合がある。
**ネットワークドライブにマップ**してから Syncthing に渡す。

```
エクスプローラー → ネットワークドライブの割り当て
  ドライブ: Z: （空いている文字）
  フォルダー: <NAS の UNC パス>
```

Syncthing で監視するパスは `paths.yaml` の `windows_mapped`（例: `Z:\under.iphone`）。

### 1-B. Windows: Syncthing フォルダ追加

Syncthing GUI（http://127.0.0.1:8384）で:

| 項目 | 値 |
| --- | --- |
| フォルダラベル | `siftivex-under-iphone` |
| フォルダ ID | `siftivex-under-iphone` |
| フォルダパス | `paths.yaml` の Windows 側パス |
| フォルダの種類 | 送信のみ または 送信と受信 |

初回は **送信のみ**（Windows → サーバー）で十分。双方向にしない。

**.stignore**（Windows 側フォルダに配置）:

```
// config/syncthing-under.iphone.stignore をコピー
```

### 1-C. サーバー: Syncthing フォルダ追加

| 項目 | 値 |
| --- | --- |
| フォルダラベル | `siftivex-under-iphone` |
| フォルダ ID | `siftivex-under-iphone` |
| フォルダパス | `paths.yaml` の `server` |
| フォルダの種類 | 受信のみ |

```bash
mkdir -p "<server-archive-path>"   # paths.yaml の archives.*.server
```

### 1-D. ペアリング

Windows ↔ サーバー の Syncthing デバイスを相互に追加し、
フォルダ `siftivex-under-iphone` を共有する。

### 1-E. 同期確認

```bash
find "<server-archive-path>" -type f \( -iname '*.jpg' -o -iname '*.png' -o -iname '*.webp' \) | wc -l
```

Syncthing GUI で「同期完了」を確認してから次へ。

---

## Step 2: Siftivex 設定を更新

同期完了後、サーバー上の siftivex リポジトリで:

```bash
make task-0.1    # manifest 再生成
make task-0.2    # DB 初期化（初回のみ）
make task-0.2b   # manifest → DB 投入
.venv/bin/python scripts/embed.py
.venv/bin/python scripts/search_test.py --query "your query"
```

`config/phase0.yaml` の `sources[].path` は `paths.yaml` の server パスと一致させる。

---

## Step 3: 以降のフォルダ追加

### pixiv ブクマ

| 項目 | 値 |
| --- | --- |
| Syncthing ID | `paths.yaml` → `syncthing_folder_id` |
| route タグ | `route/pixiv` |

ファイル名パーサー・sidecar 優先順位は [folder-rules.md](../specs/folder-rules.md) 参照。

**.stignore**（Windows 側フォルダに配置）:

```
// config/syncthing-pixiv.stignore をコピー
```

`result-total*` / `*.csv` / `*.py` を同期対象外にする（エクスポート・作業ファイル）。

### iCloud Photos（後回し）

容量が大きいため、Phase 1 本番投入前または必要になってから同期。
`.stignore` で Live Photos の動画部分等を除外する検討余地あり。

---

## 同期しないもの

| パス | 理由 |
| --- | --- |
| `data/siftivex.db` | サーバー上で生成 |
| `data/lance/` | 同上 |
| `.venv/` | 環境依存 |
| `config/paths.yaml` | ローカルパス含む |
| `config/phase0.yaml` | ローカルパス含む |

---

## トラブルシューティング

| 症状 | 対処 |
| --- | --- |
| Syncthing が UNC を開けない | ネットワークドライブ（Z:）にマップ |
| サーバー側フォルダが空 | ペアリング・フォルダ共有・受信のみ設定を確認 |
| 同期が遅い | 初回のみ。以降は差分同期 |
| NAS がスリープで切れる | NAS の電源管理設定を確認 |
| pixiv が途中で「準備中」のまま | **ファイル名が長すぎる**（Linux 上限 255 バイト）。下記 |

### pixiv ファイル名が長すぎる（`file name too long`）

pixiv ダウンローダー形式はタグ込みで 255 バイトを超えやすく、Linux サーバー側 Syncthing が完了しない。

**方針**: Windows（送信側）で短いファイル名 + **sidecar JSON** にメタデータを退避してから同期する。

#### 準備（リポジトリ clone 不要）

1. GitHub 上で [scripts/pixiv_migrate_standalone.py](../../scripts/pixiv_migrate_standalone.py) を開き **Raw** から保存  
   （または Release から同ファイルを取得）
2. Python 3.10+ が入っていることを確認（`py -3 --version`）

#### 実行

1. Syncthing の pixiv フォルダを **一時停止**（Windows / サーバー両方）
2. ドライラン（`<PIXIV_FOLDER>` は `paths.yaml` の Windows 側 pixiv パス）:

```powershell
py -3 pixiv_migrate_standalone.py "<PIXIV_FOLDER>"
```

3. 問題なければ適用:

```powershell
py -3 pixiv_migrate_standalone.py "<PIXIV_FOLDER>" --apply
```

4. Syncthing **Rescan** → 再開

| 変更前 | 変更後 |
| --- | --- |
| `date_2007-09-17id_4826_p0user_..._tags_....jpg` | `4826_p0.jpg` |
| （メタデータ） | `4826_p0.pixiv.json`（同フォルダ） |

`--all` で全ファイルを短名化、`--min-bytes 240`（デフォルト）で長い名前だけ対象。

取り込み時は `image_metadata` + sidecar を読む（Phase 1）。パーサー: `src/siftivex/pixiv_filename.py`

---

## 関連ファイル

- [config/paths.yaml.example](../../config/paths.yaml.example) — パス対応の設定テンプレート（ローカル用にコピー）
- [config/folder_rules.yaml.example](../../config/folder_rules.yaml.example) — 取り込みルール
- [config/syncthing-under.iphone.stignore](../../config/syncthing-under.iphone.stignore) — under.iphone 同期除外
- [config/syncthing-pixiv.stignore](../../config/syncthing-pixiv.stignore) — pixiv 同期除外
- [scripts/pixiv_migrate_standalone.py](../../scripts/pixiv_migrate_standalone.py) — Windows 用単体移行スクリプト
