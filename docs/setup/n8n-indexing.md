# n8n インデックスワークフロー

> Phase 1 定期実行。**import 用 JSON**: [`n8n/workflows/`](../../n8n/workflows/)

## 前提

- siftivex: `/home/objtus/siftivex`（環境に合わせて JSON 内パスを置換）
- Python venv: `.venv/bin/python`
- `config/paths.yaml` / `config/folder_rules.yaml` 設定済み
- n8n **Execute Command** ノード有効（セルフホストで `N8N_DISABLE_PRODUCTION_MAIN_PROCESS` 等の制限に注意）

## エントリポイント

すべて [`scripts/n8n_task.py`](../../scripts/n8n_task.py) 経由（**PID ロック付き**。重複起動時は exit 0 でスキップ）。

| サブコマンド | 用途 | 推奨間隔 |
|---|---|---|
| `ingest` | 新規・mtime 変更ファイルのみ ingest | 20 分 |
| `embed` | `indexed_at IS NULL` を CLIP embed | 1 時間 |
| `vlm` | `index_jobs` VLM キュー消化 | 5 分（少量） |
| `mark-missing` | ファイル消失を `status=missing` | 1 日 |
| `status` | JSON 監視出力 | 手動 / 監視用 |

```bash
cd ~/siftivex
.venv/bin/python scripts/n8n_task.py status
.venv/bin/python scripts/n8n_task.py ingest --limit 500
.venv/bin/python scripts/n8n_task.py embed --limit 200
.venv/bin/python scripts/n8n_task.py vlm --limit 5 --route route/under-iphone
```

ログ: `data/batch/n8n-*.log`

## n8n インポート手順

1. n8n UI → **Workflows** → **Import from File**
2. 以下を順にインポート（パスが `/home/objtus/siftivex` でなければ Execute Command を編集）:
   - `n8n/workflows/siftivex-ingest-sync.json`
   - `n8n/workflows/siftivex-embed-pending.json`
   - `n8n/workflows/siftivex-vlm-queue.json`
   - `n8n/workflows/siftivex-mark-missing.json`
3. 各ワークフローを **Active** にする
4. 初回: `ingest` → `embed` が 1 回ずつ成功するか手動実行で確認

## ワークフロー概要

| ファイル | スケジュール | 内容 |
|---|---|---|
| siftivex-ingest-sync | 20 分 | 差分 ingest（両 archive） |
| siftivex-embed-pending | 毎時 :15 | embed 最大 200 枚 |
| siftivex-vlm-queue | 5 分 | under.iphone VLM 最大 5 件（pixiv は Phase 2） |
| siftivex-mark-missing | 毎日 04:00 | 消失ファイル検出 |

## n8n が使えない場合（現状 objtus-server）

**port 5678 で n8n は listen していません**（未インストール or 停止中）。  
`192.168.11.150` にタイムアウトするのは正常で、**Phase 1 の自動化は cron で代替**できます（`n8n_task.py` は共通）。

### cron セットアップ（推奨）

```bash
crontab -e
```

以下を貼り付け（[`scripts/cron/siftivex-indexing.cron.example`](../../scripts/cron/siftivex-indexing.cron.example) と同内容）:

```cron
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

*/20 * * * * cd /home/objtus/siftivex && .venv/bin/python scripts/n8n_task.py ingest --limit 500 >> data/batch/cron-ingest.log 2>&1
15 * * * * cd /home/objtus/siftivex && .venv/bin/python scripts/n8n_task.py embed --limit 200 >> data/batch/cron-embed.log 2>&1
*/5 * * * * cd /home/objtus/siftivex && .venv/bin/python scripts/n8n_task.py vlm --limit 5 --route route/under-iphone >> data/batch/cron-vlm.log 2>&1
0 4 * * * cd /home/objtus/siftivex && .venv/bin/python scripts/n8n_task.py mark-missing >> data/batch/cron-missing.log 2>&1
```

確認:

```bash
crontab -l
# 20分待つか、手動で1行実行
cd ~/siftivex && .venv/bin/python scripts/n8n_task.py mark-missing
tail data/batch/cron-missing.log
```

VLM 行は llama-server 不要なら `#` でコメントアウト可（pixiv VLM は Phase 2）。

---

## cron 代替

n8n が使えない場合: [`scripts/cron/siftivex-indexing.cron.example`](../../scripts/cron/siftivex-indexing.cron.example) を `crontab -e` に追記。

## 注意

- **ingest / embed / vlm は同時刻に多重起動しない**（`n8n_task.py` がロックで防ぐが、時間帯をずらす）
- 初回 bulk（4 万枚）は **手動** `make batch-archive` で完了済み。以降は差分のみ
- pixiv VLM（~36k）は Phase 2。キューに `--route route/pixiv` を追加するまで VLM WF は under.iphone のみ
- API 監視: `curl http://127.0.0.1:8787/api/index/status`

## 手動（初回 bulk — 完了済み）

```bash
make batch-archive BATCH_ARCHIVE=pixiv_bookmarks
make vlm-overnight VLM_ROUTE=route/under-iphone
```
