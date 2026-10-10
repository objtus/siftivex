#!/usr/bin/env python3
"""G30 review HTML: filename (JA) vs tagger (EN booru) vs VLM auto."""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from siftivex.paths import PHASE0_GOLD, PHASE0_REVIEW, PHASE0_RESULTS  # noqa: E402


def thumb(path: Path) -> str | None:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((240, 240))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=78)
            return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception:
        return None


def chips(tags: list, cls: str, *, scores: bool = False) -> str:
    if not tags:
        return "<span class='empty'>—</span>"
    parts = []
    for t in tags[:30]:
        if isinstance(t, dict):
            label = html.escape(str(t.get("tag", "")))
            if scores and "score" in t:
                label += f" ({t['score']:.2f})"
        else:
            label = html.escape(str(t))
        parts.append(f"<span class='chip {cls}'>{label}</span>")
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=PHASE0_GOLD / "g30.json")
    parser.add_argument("--tagger-report", type=Path, default=PHASE0_RESULTS / "model_stack_pilot_tagger_m300.json")
    parser.add_argument("--output", type=Path, default=PHASE0_REVIEW / "pilot_g30_review.html")
    args = parser.parse_args()

    g30 = json.loads(args.gold.read_text(encoding="utf-8"))["items"]
    tagger_by_path: dict[str, list] = {}
    if args.tagger_report.is_file():
        for row in json.loads(args.tagger_report.read_text(encoding="utf-8")).get("per_image") or []:
            if row.get("tagger_tags"):
                tagger_by_path[row["source_path"]] = row["tagger_tags"]

    cards = []
    for i, item in enumerate(g30, 1):
        sp = item["source_path"]
        p = Path(sp)
        t = thumb(p) if p.is_file() else None
        img = f"<img src='{t}' alt=''>" if t else "<div class='noimg'>no file</div>"
        tagger = tagger_by_path.get(sp, [])
        cards.append(
            f"""
        <article class="card" id="g30-{i}">
          <div class="thumb">{img}</div>
          <div class="body">
            <h3>#{i} {html.escape(item.get('file_name') or p.name)}</h3>
            <p class="path"><code>{html.escape(sp)}</code></p>
            <section><h4>filename（日本語・確定）</h4>{chips(item.get('tags_filename') or [], 'fn')}</section>
            <section><h4>tagger（英語 booru）</h4>{chips(tagger, 'tagger', scores=True)}</section>
            <section><h4>VLM auto（参考）</h4>{chips(item.get('tags_auto') or [], 'vlm')}</section>
            <section><h4>namespace auto（弱正解）</h4>{chips(item.get('namespace_auto') or [], 'ns')}</section>
            <textarea class="notes" placeholder="目視メモ: tagger 有用 / filename 重複 / 検索キー案…"></textarea>
          </div>
        </article>"""
        )

    page = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<title>G30 — filename vs tagger</title>
<style>
body {{ font-family: system-ui,sans-serif; background:#111; color:#eee; margin:1rem; max-width:1100px; }}
.card {{ border-bottom:1px solid #333; padding:1.2rem 0; display:flex; gap:1rem; }}
.thumb img {{ max-width:200px; border-radius:8px; }}
.chip {{ display:inline-block; margin:2px; padding:2px 8px; border-radius:4px; font-size:12px; }}
.chip.fn {{ background:#4a3a2a; }}
.chip.tagger {{ background:#1e4d3a; }}
.chip.vlm {{ background:#2a3a5a; }}
.chip.ns {{ background:#3a2a4a; }}
.notes {{ width:100%; min-height:3em; margin-top:8px; background:#222; color:#eee; border:1px solid #444; }}
h4 {{ margin:8px 0 4px; font-size:13px; color:#aaa; }}
.intro {{ background:#1a1a2a; padding:12px; border-radius:8px; margin-bottom:1rem; }}
</style></head><body>
<h1>G30 目視レビュー</h1>
<div class="intro">
  <p><strong>filename</strong> = 取り込み前の日本語タグ（検索・UI の母語）。<strong>tagger</strong> = booru 英語（密度・類似・外部連携）。重複は別レイヤーとして共存させ、検索は両方インデックス。</p>
</div>
{''.join(cards)}
</body></html>"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"Wrote {args.output} ({len(g30)} cards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
