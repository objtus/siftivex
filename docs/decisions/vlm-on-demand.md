# VLM タグ付け: オンデマンド運用

> **決定日**: 2026-09-06  
> **状態**: Phase 2 実装予定  
> **参照**: [indexing.md](../specs/indexing.md), [tags.md](../specs/tags.md), [api.md](../specs/api.md)

## 背景

- Phase 1 bulk で pixiv ~36k の VLM キューが残存。全件 cron/n8n 常時実行は **GPU 負荷・時間（~1週間規模）** が大きい。
- llama-server（Qwen3.6 35B 等）は **ユーザーが別用途で起動・停止・モデル差し替え** する。siftivex は接続先を `config/vlm.yaml` で追従するのみ。
- Phase 0/1 で cron 5 分ごとの VLM は **空振り・DB 競合・モデル未起動時の fail** が起きうる。

## 決定

| 工程 | 自動化 | 備考 |
|---|---|---|
| ingest | ✅ cron（20 分） | 新規ファイル検知 → DB + サムネ + **VLM キューに積むだけ** |
| embed | ✅ cron（毎時） | `indexed_at IS NULL` を消化（キュー空なら即終了） |
| **VLM** | ❌ cron 常時実行 | **Web UI / API からの手動起動のみ** |
| mark-missing | ✅ cron（日次） | 変更なし |

**ingest はタグ付けしない。** キュー（`index_jobs` / `vlm_caption IS NULL`）に載せ、ユーザーが明示的に VLM バッチを開始する。

## llama-server / モデル

- **起動・停止・モデル選択はユーザー管理**（siftivex 外）。
- siftivex は `config/vlm.yaml` の `base_url` + `model` で OpenAI 互換 API に接続。
- モデル差し替え時: `vlm.yaml` の `model` を llama-server のロードモデルと一致させる。プロンプトは Qwen3.6 vision 向け — 別モデルでは JSON 失敗率・タグ品質が変わる想定。
- VLM 開始前に API が `/v1/models` に応答しない場合 → **即エラー**（バックグラウンドジョブを開始しない）。

## Phase 2: Web UI からの手動 VLM

### UX（案）

設定画面またはインデックス管理パネル:

```
ルート: [ pixiv ▼ ]
件数:   [ 1000 ]  （空 = 上限なし / キュー尽きるまで）
終了:   [ 02:00 まで □ ]  （任意・翌日跨ぎ可）

未タグ: 36,417 件   [ タグ付け開始 ]  [ 停止 ]
進捗:   120 / 1000  ok=115 fail=5   残り ~45 分
```

**ユースケース例**

- 寝る前に「1000 件タグ付け」→ `max_images=1000`
- 「02:00 まで回す」→ `until=02:00`（バッチ境界で停止）
- 両方指定 → **先に満たした条件で停止**

### API（Phase 2 草案）

| Method | Path | 説明 |
|---|---|---|
| POST | `/api/jobs/vlm/start` | バックグラウンド VLM 開始 |
| GET | `/api/jobs/vlm/status` | 実行中/進捗/締切 |
| POST | `/api/jobs/vlm/stop` | 次バッチ前に graceful 停止 |

**POST `/api/jobs/vlm/start` ボディ（案）**

```json
{
  "route_tag": "route/pixiv",
  "max_images": 1000,
  "until": "2026-09-07T02:00:00+09:00",
  "batch_size": 10
}
```

| フィールド | 必須 | 説明 |
|---|---|---|
| `route_tag` | はい | 例: `route/pixiv`, `route/under-iphone` |
| `max_images` | いいえ | 0 または省略 = キュー尽きるまで |
| `until` | いいえ | ISO 8601。現在時刻を過ぎたら次バッチ前に停止 |
| `batch_size` | いいえ | 既定 10 |

**GET `/api/jobs/vlm/status` レスポンス（案）**

```json
{
  "running": true,
  "route_tag": "route/pixiv",
  "processed": 120,
  "ok": 115,
  "fail": 5,
  "max_images": 1000,
  "until": "2026-09-07T02:00:00+09:00",
  "started_at": "...",
  "last_error": null
}
```

### 実装方針

- 既存 [`run_vlm_overnight.py`](../../scripts/run_vlm_overnight.py) を拡張:
  - `--until ISO8601` を追加（ループ先頭で `now < until` を確認）
  - `--max-images` は既存
- API は subprocess または asyncio タスクで上記を起動。**`job_lock("vlm-overnight")` で二重起動防止**。
- 停止: フラグファイル or キャンセルイベント → 次バッチ開始前に break。
- CLI でも同等操作可能（UI なしでも運用可）:

```bash
.venv/bin/python scripts/run_vlm_overnight.py \
  --route route/pixiv --max-images 1000 --until 2026-09-07T02:00
```

### 停止の粒度

- **バッチ単位**（例: 10 枚）で止める。締切 02:00 直前にバッチが始まった場合、そのバッチ完走後に停止（最大 1 バッチ分オーバー）。
- embed / ingest の cron とは **同時実行を避ける**（DB ロック）。VLM 実行中は embed cron がロック待ち or スキップ。

## cron から VLM を外す

Phase 1 クローズ時点の crontab から VLM 行は **コメントアウト推奨**:

```cron
# */5 * * * * ... n8n_task.py vlm ...   # オンデマンド運用のため無効
```

## Phase 2 タスク対応

→ [phase-2.md](../plans/phase-2.md) タスク 2.8「VLM オンデマンド UI + API」

## 関連

- [n8n-indexing.md](../setup/n8n-indexing.md) — ingest/embed cron のみ
- [phase-1-prep.md](phase-1-prep.md) — 初回 bulk 実績
