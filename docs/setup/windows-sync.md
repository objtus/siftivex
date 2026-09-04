# Windows ↔ サーバー 画像同期

> **参照**: [blueprint.md](../../blueprint.md) §推奨技術スタック（Syncthing）

## 方針

- 元画像は **Windows / NAS 上が正本**。サーバーへ Syncthing で同期
- DB・embedding・LanceDB は **サーバー上のみ**（同期しない）
- まず **under.iphone** から開始。以降順次追加

## パス対応表


| 名前            | Windows 側（正本）                                           | サーバー側（同期先）                                           | route タグ             | 状態             |
| ------------- | ------------------------------------------------------- | ---------------------------------------------------- | -------------------- | -------------- |
| under.iphone  | `\\192.168.11.36\objtus@protonmail.com\画像\under.iphone` | `/home/objtus/Sync/siftivex-archive/under.iphone`    | `route/under-iphone` | **Phase 0 対象** |
| pixiv ブクマ     | `D:\公開ブクマ`                                              | `/home/objtus/Sync/siftivex-archive/pixiv-bookmarks` | `route/pixiv`        | 後続             |
| iCloud Photos | `C:\Users\objtus\Pictures\iCloud Photos`                | `/home/objtus/Sync/siftivex-archive/icloud-photos`   | `route/icloud`       | 後回し（容量大）       |


サーバー側のルート: `/home/objtus/Sync/siftivex-archive/`

---

## Step 1: under.iphone（NAS → サーバー）

### 1-A. Windows: NAS をドライブレターに割り当て

Syncthing は UNC パス（`\\server\share`）を直接監視できない場合がある。
**ネットワークドライブにマップ**してから Syncthing に渡す。

```
エクスプローラー → ネットワークドライブの割り当て
  ドライブ: Z: （空いている文字）
  フォルダー: \\192.168.11.36\objtus@protonmail.com\画像
```

Syncthing で監視するパス:

```
Z:\under.iphone
```

### 1-B. Windows: Syncthing フォルダ追加

Syncthing GUI（[http://127.0.0.1:8384）で](http://127.0.0.1:8384）で):


| 項目      | 値                       |
| ------- | ----------------------- |
| フォルダラベル | `siftivex-under-iphone` |
| フォルダ ID | `siftivex-under-iphone` |
| フォルダパス  | `Z:\under.iphone`       |
| フォルダの種類 | 送信のみ または 送信と受信          |


初回は **送信のみ**（Windows → サーバー）で十分。双方向にしない。

**.stignore**（Windows 側フォルダに配置）:

```
// config/syncthing-under.iphone.stignore をコピー
```

### 1-C. サーバー: Syncthing フォルダ追加

Syncthing GUI（Tailscale 経由 or localhost:8384）で:


| 項目      | 値                                                 |
| ------- | ------------------------------------------------- |
| フォルダラベル | `siftivex-under-iphone`                           |
| フォルダ ID | `siftivex-under-iphone`                           |
| フォルダパス  | `/home/objtus/Sync/siftivex-archive/under.iphone` |
| フォルダの種類 | 受信のみ                                              |


```bash
mkdir -p /home/objtus/Sync/siftivex-archive/under.iphone
```

### 1-D. ペアリング

Windows ↔ サーバー の Syncthing デバイスを相互に追加し、
フォルダ `siftivex-under-iphone` を共有する。

### 1-E. 同期確認

```bash
# サーバーで
find /home/objtus/Sync/siftivex-archive/under.iphone -type f \
  \( -iname '*.jpg' -o -iname '*.png' -o -iname '*.webp' \) | wc -l
```

Syncthing GUI で「同期完了」を確認してから次へ。

---

## Step 2: Siftivex 設定を更新

同期完了後:

```bash
cd /path/to/siftivex
make task-0.1    # manifest 再生成（300枚サンプル）
make task-0.2    # DB 初期化（初回のみ）
make task-0.2b   # manifest → DB 投入
SIFTIVEX_DEVICE=cuda:1 .venv/bin/python scripts/embed.py
SIFTIVEX_DEVICE=cuda:1 .venv/bin/python scripts/search_test.py --query "your query"
```

**2026-09-04 実行結果（under.iphone）**

| 項目 | 値 |
|---|---|
| 同期済み総数 | 3,994 枚（3.5 GB） |
| Phase 0 サンプル | 300 枚（manifest） |
| DB 投入 | 299 枚（1 件は重複 hash） |
| embedding 成功 | 298 枚（1 件読み取り不可: `IMG5058.JPG`） |
| 処理速度 | ~0.037 s/枚（cuda:1） |

`config/phase0.yaml` の該当行:

```yaml
sources:
  - route_tag: route/under-iphone
    path: /home/objtus/Sync/siftivex-archive/under.iphone
    count: 300
```

---

## Step 3: 以降のフォルダ追加

### pixiv ブクマ（`D:\公開ブクマ`）


| 項目           | 値                                                    |
| ------------ | ---------------------------------------------------- |
| Syncthing ID | `siftivex-pixiv-bookmarks`                           |
| Windows      | `D:\公開ブクマ`                                           |
| サーバー         | `/home/objtus/Sync/siftivex-archive/pixiv-bookmarks` |
| route タグ     | `route/pixiv`                                        |


ファイル名パーサー（pixiv ダウンローダー形式）は [folder-rules.md](../specs/folder-rules.md) 参照。

### iCloud Photos（後回し）

容量が大きいため、Phase 1 本番投入前または必要になってから同期。
`.stignore` で Live Photos の動画部分等を除外する検討余地あり。

---

## 同期しないもの


| パス                   | 理由       |
| -------------------- | -------- |
| `data/siftivex.db`   | サーバー上で生成 |
| `data/lance/`        | 同上       |
| `.venv/`             | 環境依存     |
| `config/phase0.yaml` | ローカルパス含む |


---

## トラブルシューティング


| 症状                    | 対処                     |
| --------------------- | ---------------------- |
| Syncthing が UNC を開けない | ネットワークドライブ（Z:）にマップ     |
| サーバー側フォルダが空           | ペアリング・フォルダ共有・受信のみ設定を確認 |
| 同期が遅い                 | 初回のみ。以降は差分同期           |
| NAS がスリープで切れる         | NAS の電源管理設定を確認         |


## 関連ファイル

- [config/paths.yaml.example](../../config/paths.yaml.example) — パス対応の設定テンプレート
- [config/folder_rules.yaml.example](../../config/folder_rules.yaml.example) — 取り込みルール
- [config/syncthing-under.iphone.stignore](../../config/syncthing-under.iphone.stignore) — 同期除外

