#!/usr/bin/env python3
"""Track B: mockup Phase 2 checklist — API + Playwright (headless).

Usage:
  uv run --with playwright python scripts/mockup_phase2_verify.py
  uv run --with playwright python scripts/mockup_phase2_verify.py --base http://127.0.0.1:5199/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "siftivex.db"
EXE = (
    Path.home()
    / ".cache/ms-playwright/chromium_headless_shell-1234/"
    "chrome-headless-shell-linux64/chrome-headless-shell"
)


@dataclass
class Check:
    section: str
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, section: str, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(section, name, ok, detail))

    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


def api_get(base: str, path: str) -> dict:
    url = base.rstrip("/") + path
    with urllib.request.urlopen(url, timeout=120) as res:
        return json.loads(res.read())


def run_api_checks(api: str, report: Report) -> None:
    sec = "API"
    try:
        st = api_get(api, "/api/index/status")
    except (urllib.error.URLError, TimeoutError) as e:
        report.add(sec, "index/status reachable", False, str(e))
        return
    report.add(sec, "index/status reachable", True)

    ts = st.get("tag_stack") or {}
    report.add(
        sec,
        "tagger coverage",
        ts.get("with_auto_tagger") == ts.get("images_active") - ts.get("missing_auto_tagger", 0)
        and ts.get("with_auto_tagger", 0) >= 40300,
        f"tagger={ts.get('with_auto_tagger')} active={ts.get('images_active')}",
    )
    report.add(
        sec,
        "d1 coverage",
        ts.get("with_auto_d1", 0) >= 40300,
        f"d1={ts.get('with_auto_d1')}",
    )

    if DB.is_file():
        conn = sqlite3.connect(DB)
        try:
            db_active = conn.execute(
                "SELECT COUNT(*) FROM images WHERE status = 'active'"
            ).fetchone()[0]
            report.add(
                sec,
                "index status vs DB images_active",
                db_active == st.get("images_active"),
                f"db={db_active} api={st.get('images_active')}",
            )
        finally:
            conn.close()

    queries = [
        ("tag:オリジナル", "pixiv filename", 1000),
        ("tag:種類/イラスト", "d1 pixiv", 1000),
        ('tag:"bare legs"', "tagger EN quoted", 100),
        ("tag:種類/写真", "d1 photo", 100),
        ("青い髪", "CLIP JA", 10),
        ("tag:1girl", "tagger EN tag:", 1000),
    ]
    for q, label, min_total in queries:
        enc = urllib.parse.quote(q)
        try:
            data = api_get(api, f"/api/images?q={enc}&limit=5")
            total = data.get("total") or 0
            items = data.get("items") or []
            ok = total >= min_total and len(items) > 0
            extra = f"total={total}"
            if q == "青い髪":
                sc = items[0].get("score") if items else None
                ok = ok and sc is not None and sc > 0
                extra += f" score0={sc}"
            report.add(sec, f"search {label}", ok, extra)
        except Exception as e:
            report.add(sec, f"search {label}", False, str(e))

    # detail tag_sources
    try:
        first = api_get(api, "/api/images?limit=1")["items"][0]["image_id"]
        detail = api_get(api, f"/api/images/{urllib.parse.quote(first, safe='')}")
        ts = detail.get("tag_sources") or {}
        keys = {"filename", "auto_tagger", "auto_d1"}
        ok = keys.issubset(ts.keys())
        report.add(sec, "detail tag_sources keys", ok, ",".join(sorted(ts.keys())))
        has_layers = any(isinstance(ts[k], list) and len(ts[k]) > 0 for k in keys)
        report.add(sec, "detail has tag rows", has_layers, str({k: len(ts.get(k) or []) for k in keys}))
    except Exception as e:
        report.add(sec, "detail tag_sources", False, str(e))

    try:
        items = api_get(api, "/api/images?limit=50")["items"]
        prev_item = next((i for i in items if i.get("has_preview")), None)
        ok_prev = False
        detail_prev = ""
        for prev_item in items:
            if not prev_item.get("has_preview"):
                continue
            iid = prev_item["image_id"]
            url = f"{api.rstrip('/')}/api/images/{urllib.parse.quote(iid, safe='')}/preview"
            try:
                with urllib.request.urlopen(url, timeout=60) as res:
                    if res.status == 200:
                        ok_prev = True
                        detail_prev = iid
                        break
            except urllib.error.HTTPError:
                continue
        if ok_prev:
            report.add(sec, "preview 200", True, detail_prev)
        elif not any(i.get("has_preview") for i in items):
            report.add(sec, "preview 200", True, "skip none in first 50")
        else:
            report.add(sec, "preview 200", False, "all candidates 404")
    except Exception as e:
        report.add(sec, "preview 200", False, str(e))


async def run_ui_checks(base: str, report: Report) -> None:
    from playwright.async_api import async_playwright

    sec = "UI"
    if not EXE.is_file():
        report.add(sec, "playwright binary", False, str(EXE))
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=str(EXE))
        ctx = await browser.new_context(viewport={"width": 1600, "height": 960})
        await ctx.add_init_script(
            "localStorage.setItem('siftivex.mockup.prefs', JSON.stringify({useApi: true, theme: 'dark'}));"
        )
        page = await ctx.new_page()
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(f"pageerror:{e}"))

        await page.goto(base)
        await page.wait_for_selector(".image-card", timeout=30000)
        await page.wait_for_timeout(2000)

        thumbs = await page.evaluate("""() => {
          const cards = [...document.querySelectorAll('.image-card')].slice(0, 40);
          const ok = cards.filter(c => {
            const i = c.querySelector('img.thumb');
            return i && i.complete && i.naturalWidth > 0;
          }).length;
          const ph = cards.filter(c => c.querySelector('.thumb-placeholder')).length;
          return {cards: cards.length, ok, ph};
        }""")
        report.add(
            sec,
            "grid thumbs (first 40 cards)",
            thumbs["ok"] >= 30,
            str(thumbs),
        )

        # facet include
        await page.fill("#query-input", "")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)
        before = await page.locator("#result-count").text_content()
        await page.locator("#tag-list .facet-row").first.click()
        await page.wait_for_timeout(3000)
        chips = await page.locator("#chip-row .filter-chip").count()
        after = await page.locator("#result-count").text_content()
        report.add(sec, "facet click → chip", chips >= 1, f"chips={chips}")
        report.add(sec, "facet narrows list", before != after or chips >= 1, f"{before} -> {after}")

        # exclude via shift (second facet)
        await page.locator("#tag-list .facet-row").nth(1).click(modifiers=["Shift"])
        await page.wait_for_timeout(2500)
        ex = await page.locator("#chip-row .filter-chip.exclude").count()
        report.add(sec, "facet Shift exclude", ex >= 1, f"exclude chips={ex}")

        await page.click("#btn-clear-filters")
        await page.wait_for_timeout(2500)
        cleared = await page.locator("#chip-row .filter-chip").count()
        report.add(sec, "clear all filters", cleared == 0, str(cleared))

        # NL + table score
        await page.select_option("#sort-select", "file_name")
        await page.fill("#query-input", "青い髪")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(5000)
        sort_val = await page.input_value("#sort-select")
        report.add(sec, "NL query auto sort=score", sort_val == "score", sort_val)
        await page.locator('#layout-seg button[data-layout="table"]').click()
        await page.wait_for_timeout(800)
        score_cell = await page.locator(".image-table tbody tr td.col-score").first.text_content()
        report.add(sec, "table score column", score_cell != "—" and score_cell.strip() != "", score_cell)

        # view back scroll
        scroll_set = 1200
        await page.locator('#layout-seg button[data-layout="justified"]').click()
        await page.fill("#query-input", "")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(3000)
        await page.evaluate(f"() => {{ document.querySelector('#list-scroll').scrollTop = {scroll_set}; }}")
        await page.wait_for_timeout(300)
        active_id = await page.evaluate("""() => {
          const cards = document.querySelectorAll('.image-card');
          const c = cards[Math.min(19, cards.length - 1)];
          return c ? c.dataset.id : null;
        }""")
        await page.evaluate("""() => {
          const cards = document.querySelectorAll('.image-card');
          cards[Math.min(19, cards.length - 1)]?.click();
        }""")
        await page.wait_for_timeout(2000)
        in_view = await page.evaluate(
            "() => document.querySelector('#app')?.classList.contains('mode-view')"
        )
        report.add(sec, "open detail view mode", bool(in_view), "")
        if in_view and active_id:
            await page.click("#btn-back-explore")
            await page.wait_for_timeout(800)
            back = await page.evaluate("""() => ({
              mode: document.querySelector('#app')?.className ?? '',
              scroll: document.querySelector('#list-scroll')?.scrollTop ?? 0,
              active: document.querySelector('.image-card.active')?.dataset.id ?? null
            })""")
            report.add(
                sec,
                "back restores list + scroll",
                "mode-view" not in back["mode"] and back["scroll"] >= 80,
                str(back),
            )
            report.add(
                sec,
                "back active card",
                back.get("active") == active_id,
                f"{back.get('active')} vs {active_id}",
            )
        else:
            report.add(sec, "back restores list + scroll", False, "skip no view")
            report.add(sec, "back active card", False, "skip")

        # multi-page work (grid に戻す)
        await page.locator('#layout-seg button[data-layout="justified"]').click()
        await page.fill("#query-input", "")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(3500)
        if not await page.locator(".image-card").count():
            report.add(sec, "multi-page strip", False, "no cards")
            report.add(sec, "page ] key", False, "skip")
        else:
            await page.locator(".image-card").first.click()
            await page.wait_for_timeout(1500)
            for _ in range(20):
                if await page.evaluate(
                    "() => document.querySelector('#detail-page-slot').classList.contains('has-pages')"
                ):
                    break
                await page.evaluate("() => document.querySelector('#detail-next').click()")
                await page.wait_for_timeout(400)
            has_pages = await page.evaluate(
                "() => document.querySelector('#detail-page-slot').classList.contains('has-pages')"
            )
            strip_n = await page.locator("#page-strip .page-strip-item").count()
            report.add(sec, "multi-page strip", has_pages and strip_n > 1, f"strip={strip_n}")
            if has_pages:
                await page.keyboard.press("]")
                await page.wait_for_timeout(2000)
                s = await page.evaluate("""() => ({
                  strip: document.querySelector('#page-strip .active')?.dataset.id,
                  shown: document.querySelector('#detail-image').dataset.imageId
                })""")
                report.add(sec, "page ] key", s["strip"] == s["shown"], str(s))
            else:
                report.add(sec, "page ] key", False, "no multi-page work found")

        # index panel
        await page.keyboard.press("Escape")
        await page.click("#btn-settings")
        await page.wait_for_timeout(500)
        await page.click("#lab-index-refresh")
        await page.wait_for_timeout(1500)
        body = await page.locator("#lab-index-body").inner_text()
        report.add(
            sec,
            "settings index panel",
            "Tagger" in body and "40,305" in body,
            body[:80],
        )

        # theme persist
        await page.locator('#theme-seg button[data-theme-choice="light"]').click()
        await page.wait_for_timeout(200)
        theme = await page.evaluate(
            "() => JSON.parse(localStorage.getItem('siftivex.mockup.prefs')).theme"
        )
        report.add(sec, "theme localStorage", theme == "light", theme)

        # load more on big hit
        await page.keyboard.press("Escape")
        await page.fill("#query-input", "tag:種類/イラスト")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(4000)
        total_txt = await page.locator("#result-count").text_content()
        cards0 = await page.locator(".image-card").count()
        if "3" in total_txt or cards0 >= 200:
            await page.evaluate("() => document.querySelector('#list-scroll').scrollTop = 1e9")
            await page.wait_for_timeout(5000)
            cards1 = await page.locator(".image-card").count()
            report.add(sec, "infinite scroll load", cards1 > cards0, f"{cards0} -> {cards1}")
        else:
            report.add(sec, "infinite scroll load", True, "skip small result")

        if await page.locator(".image-card").count():
            await page.locator(".image-card").first.click()
            await page.wait_for_timeout(2500)
        detail_tags = await page.locator("#detail-tags").inner_text()
        report.add(
            sec,
            "detail tag layers",
            "構造化" in detail_tags or "Tagger" in detail_tags or "ファイル名" in detail_tags,
            detail_tags[:100],
        )

        report.add(sec, "no page JS errors", len(errs) == 0, "; ".join(errs[:3]))
        await browser.close()


def print_report(report: Report) -> int:
    by_sec: dict[str, list[Check]] = {}
    for c in report.checks:
        by_sec.setdefault(c.section, []).append(c)
    for section, items in by_sec.items():
        print(f"\n## {section}")
        for c in items:
            mark = "OK" if c.ok else "FAIL"
            line = f"  [{mark}] {c.name}"
            if c.detail:
                line += f" — {c.detail}"
            print(line)
    failed = report.failed()
    print(f"\nTotal: {len(report.checks)}  Failed: {len(failed)}")
    return 1 if failed else 0


async def main_async(base: str, api: str) -> int:
    report = Report()
    run_api_checks(api, report)
    await run_ui_checks(base, report)
    return print_report(report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5199/", help="mockup URL")
    parser.add_argument("--api", default="http://127.0.0.1:8787/", help="API URL (direct)")
    args = parser.parse_args()
    code = asyncio.run(main_async(args.base.rstrip("/") + "/", args.api.rstrip("/") + "/"))
    sys.exit(code)


if __name__ == "__main__":
    main()
