#!/usr/bin/env python3
"""Build HTML review page from model_stack_pilot JSON (+ optional DB tags)."""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from siftivex.db import get_connection  # noqa: E402
from siftivex.paths import DEFAULT_DB_PATH, PHASE0_REVIEW  # noqa: E402
from siftivex.tags_db import tags_grouped_by_source  # noqa: E402


def thumb_data_url(path: Path, max_size: int = 280) -> str | None:
    try:
        with Image.open(path) as img:
            if getattr(img, "is_animated", False):
                img.seek(0)
            img = img.convert("RGB")
            img.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=78)
            return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception:
        return None


def fmt_tags(tags: list | None, cls: str) -> str:
    if not tags:
        return "—"
    if tags and isinstance(tags[0], dict):
        parts = [f"{html.escape(t.get('tag', '?'))} ({t.get('score', 0):.2f})" for t in tags[:24]]
    else:
        parts = [html.escape(str(t)) for t in tags[:24]]
    return " ".join(f'<span class="chip {cls}">{p}</span>' for p in parts)


def render_card(row: dict, db_tags: dict | None) -> str:
    path = Path(row.get("source_path", ""))
    thumb = thumb_data_url(path) if path.is_file() else None
    thumb_html = f'<img src="{thumb}" alt="">' if thumb else "<div class='noimg'>no preview</div>"
    d1 = row.get("d1") or {}
    d1_ans = d1.get("answers") if isinstance(d1, dict) else None
    d1_html = html.escape(json.dumps(d1_ans, ensure_ascii=False)[:800]) if d1_ans else "—"
    db_html = ""
    if db_tags:
        db_html = f"""
        <div class="row"><strong>DB filename</strong> {fmt_tags(db_tags.get('filename'), 'fn')}</div>
        <div class="row"><strong>DB auto (VLM)</strong> {fmt_tags(db_tags.get('auto'), 'vlm')}</div>
        """
    return f"""
    <article class="card">
      <div class="thumb">{thumb_html}</div>
      <div class="body">
        <code>{html.escape(str(row.get('source_path', '')))}</code>
        <div class="row"><strong>tagger</strong> {fmt_tags(row.get('tagger_tags'), 'tagger')}</div>
        {db_html}
        <div class="row"><strong>d1 answers</strong><pre class="d1">{d1_html}</pre></div>
        <div class="row"><strong>legacy VLM</strong> {html.escape(str(row.get('legacy_vlm')))}</div>
      </div>
    </article>
    """


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate pilot review HTML")
    parser.add_argument("report", type=Path, help="model_stack_pilot_*.json")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, help="HTML output path")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    rows = report.get("per_image") or []
    if args.limit > 0:
        rows = rows[: args.limit]

    conn = get_connection(args.db)
    try:
        cards = []
        for row in rows:
            db_tags = None
            iid = row.get("image_id")
            if not iid:
                sp = row.get("source_path")
                if sp:
                    r = conn.execute(
                        "SELECT image_id FROM images WHERE source_path = ?",
                        (sp,),
                    ).fetchone()
                    iid = r["image_id"] if r else None
            if iid:
                db_tags = tags_grouped_by_source(conn, iid)
            cards.append(render_card(row, db_tags))
    finally:
        conn.close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output or PHASE0_REVIEW / f"pilot_{stamp}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    page = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<title>Pilot review {html.escape(args.report.name)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1rem; background: #111; color: #eee; }}
.card {{ display: flex; gap: 1rem; border-bottom: 1px solid #333; padding: 1rem 0; }}
.thumb img {{ max-width: 200px; border-radius: 6px; }}
.chip {{ display: inline-block; margin: 2px; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
.chip.tagger {{ background: #264; }}
.chip.vlm {{ background: #336; }}
.chip.fn {{ background: #443; }}
pre.d1 {{ white-space: pre-wrap; font-size: 11px; color: #ccc; }}
</style></head><body>
<h1>Pilot review</h1>
<p>Report: {html.escape(str(args.report))}</p>
<p>Hardware: {html.escape(json.dumps(report.get('hardware', {}), ensure_ascii=False))}</p>
{''.join(cards)}
</body></html>"""
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
