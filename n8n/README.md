# n8n ワークフロー

Phase 1 定期インデックス用。インポート手順は [docs/setup/n8n-indexing.md](../docs/setup/n8n-indexing.md)。

| ファイル | 用途 |
|---|---|
| `siftivex-ingest-sync.json` | 差分 ingest（20 分） |
| `siftivex-embed-pending.json` | CLIP embed（毎時） |
| `siftivex-vlm-queue.json` | VLM キュー（5 分・under.iphone） |
| `siftivex-mark-missing.json` | 消失検出（毎日） |

インポート後、Execute Command 内の `/home/objtus/siftivex` を環境に合わせて編集してください。
