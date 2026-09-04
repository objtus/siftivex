#!/usr/bin/env python3
"""Task 0.7: Generate HTML review page for manual tag evaluation."""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, PHASE0_REVIEW  # noqa: E402
from siftivex.tags_db import effective_tags  # noqa: E402


def thumbnail_data_url(path: Path, max_size: int = 320) -> str | None:
    try:
        with Image.open(path) as img:
            if getattr(img, "is_animated", False):
                img.seek(0)
            img = img.convert("RGB")
            img.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


def fetch_tag_groups(conn, image_id: str) -> dict[str, list[str]]:
    rows = conn.execute(
        "SELECT tag, source FROM image_tags WHERE image_id = ? ORDER BY source, tag",
        (image_id,),
    ).fetchall()
    groups: dict[str, list[str]] = {"filename": [], "auto": [], "other": []}
    for row in rows:
        source = row["source"]
        if source in groups:
            groups[source].append(row["tag"])
        else:
            groups["other"].append(f"[{source}] {row['tag']}")
    return groups


def render_card(item: dict) -> str:
    tags = item["tags"]
    filename_tags = " ".join(
        f'<span class="chip filename">{html.escape(t)}</span>' for t in tags["filename"]
    )
    auto_tags = " ".join(f'<span class="chip auto">{html.escape(t)}</span>' for t in tags["auto"])
    thumb = (
        f'<img src="{item["thumb"]}" alt="thumbnail">' if item["thumb"] else "<div class='noimg'>No preview</div>"
    )
    caption = html.escape(item["caption"] or "（キャプションなし）")
    file_name = html.escape(item["file_name"])
    image_id = html.escape(item["image_id"])
    status = html.escape(item["status"])

    return f"""
    <article class="card" id="{image_id}">
      <div class="thumb">{thumb}</div>
      <div class="meta">
        <div class="id">{image_id}</div>
        <div class="status">{status}</div>
        <div class="caption">{caption}</div>
        <details class="filename-details">
          <summary>ファイル名（ローカルのみ）</summary>
          <code>{file_name}</code>
        </details>
        <section>
          <h3>filename</h3>
          <div class="chips">{filename_tags or '<span class="muted">なし</span>'}</div>
        </section>
        <section>
          <h3>VLM (auto)</h3>
          <div class="chips">{auto_tags or '<span class="muted">なし</span>'}</div>
        </section>
        <section>
          <h3>評価メモ</h3>
          <textarea placeholder="OK / 修正点など"></textarea>
        </section>
      </div>
    </article>
    """


def build_html(items: list[dict], sample_size: int, seed: int) -> str:
    cards = "\n".join(render_card(item) for item in items)
    generated = datetime.now(timezone.utc).astimezone().isoformat()
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>Siftivex Phase 0 Tag Review</title>
  <style>
    body {{ font-family: sans-serif; margin: 0; background: #111; color: #eee; }}
    header {{ padding: 16px 20px; background: #1b1b1b; position: sticky; top: 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; padding: 16px; }}
    .card {{ background: #1b1b1b; border: 1px solid #333; border-radius: 8px; overflow: hidden; }}
    .thumb img {{ width: 100%; display: block; background: #000; }}
    .noimg {{ height: 180px; display: grid; place-items: center; color: #888; }}
    .meta {{ padding: 12px; display: grid; gap: 8px; }}
    .id {{ font-size: 12px; color: #aaa; word-break: break-all; }}
    .status {{ font-size: 12px; color: #8cf; }}
    .caption {{ font-size: 14px; line-height: 1.4; }}
    .filename-details summary {{ cursor: pointer; color: #aaa; font-size: 12px; }}
    .filename-details code {{ display: block; margin-top: 4px; font-size: 11px; color: #888; word-break: break-all; }}
    h3 {{ margin: 0; font-size: 12px; color: #aaa; text-transform: uppercase; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .chip {{ font-size: 12px; padding: 2px 8px; border-radius: 999px; }}
    .chip.filename {{ background: #333; }}
    .chip.auto {{ background: #264; }}
    .muted {{ color: #666; font-size: 12px; }}
    textarea {{ width: 100%; min-height: 56px; background: #111; color: #eee; border: 1px solid #444; border-radius: 4px; }}
  </style>
</head>
<body>
  <header>
    <h1>Siftivex Phase 0 — Tag Review</h1>
    <p>{len(items)} samples / seed={seed} / generated {html.escape(generated)}</p>
    <p>ファイル名は折りたたみ内。評価メモはブラウザ内のみ（保存されません）。</p>
  </header>
  <main class="grid">
    {cards}
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate tag review HTML")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--sample", type=int, default=25)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=PHASE0_REVIEW / "index.html")
    args = parser.parse_args()

    conn = get_connection(args.db)
    rows = conn.execute(
        """
        SELECT image_id, source_path, file_name, vlm_caption FROM images
        WHERE status = 'active' ORDER BY image_id
        """
    ).fetchall()

    pool = list(rows)
    rng = random.Random(args.seed)
    rng.shuffle(pool)
    sample = pool[: args.sample]

    items: list[dict] = []
    for row in sample:
        path = Path(row["source_path"])
        has_auto = conn.execute(
            "SELECT 1 FROM image_tags WHERE image_id = ? AND source = 'auto' LIMIT 1",
            (row["image_id"],),
        ).fetchone()
        items.append(
            {
                "image_id": row["image_id"],
                "file_name": row["file_name"],
                "caption": row["vlm_caption"],
                "thumb": thumbnail_data_url(path),
                "tags": fetch_tag_groups(conn, row["image_id"]),
                "status": "VLM済" if has_auto else "filenameのみ / VLM未",
            }
        )
    conn.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(items, args.sample, args.seed), encoding="utf-8")

    meta = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "sample_size": len(items),
        "seed": args.seed,
        "output": str(args.output),
        "image_ids": [i["image_id"] for i in items],
    }
    meta_path = args.output.parent / "review_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote review HTML: {args.output}")
    print(f"Meta: {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
