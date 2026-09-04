# n8n インデックスワークフロー

> Phase 1 定期実行用。実パスは `config/paths.yaml` / サーバー環境に合わせて置換する。

## 前提

- n8n は既存 objtus-server 上で稼働
- siftivex リポジトリ: `/path/to/siftivex`（例: `~/siftivex`）
- Python venv: `/path/to/siftivex/.venv/bin/python`

## ワークフロー 1: 新規ファイル ingest（15〜30 分）

```
Schedule Trigger (cron: */20 * * * *)
  → Execute Command
      cd /path/to/siftivex
      .venv/bin/python scripts/ingest.py --archive under_iphone --skip-ocr --limit 500
  → Execute Command  (pixiv 安定後)
      .venv/bin/python scripts/ingest.py --archive pixiv_bookmarks --skip-ocr --limit 500
```

初回 bulk 完了後は `--limit` で差分のみ。フルスキャンは 1 日 1 回など別ワークフローに分離可。

## ワークフロー 2: VLM キュー消化（5 分、夜間中心）

```
Schedule Trigger (cron: */5 22-7 * * *)
  → Execute Command
      cd /path/to/siftivex
      .venv/bin/python scripts/process_jobs.py --type vlm_tag --route route/under-iphone --limit 10
```

pixiv の VLM は ingest 完了後に `--route route/pixiv` を追加。

## ワークフロー 3: embed 未処理（1 時間）

```
Schedule Trigger (cron: 15 * * * *)
  → Execute Command
      cd /path/to/siftivex
      .venv/bin/python scripts/embed_pending.py --limit 200
```

## 手動（初回 bulk）

```bash
make batch-archive BATCH_ARCHIVE=pixiv_bookmarks
make vlm-overnight VLM_ROUTE=route/under-iphone
```

## 注意

- **ingest と embed を同時に複数起動しない**（`run_archive_batch.py` または lock 利用）
- VLM は GPU 負荷大 → CLIP embed バッチと時間帯をずらす
- ログ: `data/batch/*.log`

## API ヘルス確認（FastAPI 起動後）

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/api/index/status
```
