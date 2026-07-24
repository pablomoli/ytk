"""Headless smoke for the /map hierarchy. Run against a live hub:
uv run --with playwright python scripts/smoke_map.py [--base http://localhost:6969]
Asserts, in both 3D and 2D: legend sorted by size, clicking a domain label
focuses that domain (not a neighbor), drill-down and pop, intro gating."""

import argparse
import sys

from playwright.sync_api import sync_playwright

EXE = "/Users/melocoton/Library/Caches/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-mac-arm64/chrome-headless-shell"


def legend(page):
    return page.eval_on_selector_all(
        ".map-legend button:not(.map-legend-toggle):not(.sub)",
        """els => els.map(e => {
            const span = e.querySelector('span');
            const clone = e.cloneNode(true);
            clone.querySelector('span').remove();
            return {label: clone.textContent, n: +span.textContent, off: e.classList.contains('off')};
        })""",
    )


def run(page, base, suffix, name):
    page.goto(f"{base}/map{suffix}")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".map-label")
    page.wait_for_timeout(2500)
    rows = legend(page)
    ns = [r["n"] for r in rows]
    assert ns == sorted(ns, reverse=True), f"[{name}] legend not size-sorted: {ns}"
    # .first re-resolves between text_content() and click(); safe because the
    # renderer only recreates label nodes on focus/view changes, never per frame.
    lab_el = page.locator(".map-label").first
    lab_t = lab_el.text_content()
    lab_el.click()
    page.wait_for_timeout(1400)
    on = [r["label"] for r in legend(page) if not r["off"]]
    assert on == [lab_t], f"[{name}] clicked label '{lab_t}' but selected {on}"
    subs = page.locator(".map-legend button.sub")
    drilled = subs.count() > 0
    if drilled:
        subs.first.click()
        page.wait_for_timeout(1200)
        page.mouse.click(200, 850)  # empty corner: pop subtopic -> domain
        page.wait_for_timeout(1200)
        on = [r["label"] for r in legend(page) if not r["off"]]
        assert on == [lab_t], f"[{name}] empty click should pop to domain focus, got {on}"
    page.mouse.click(200, 850)  # pop domain -> overview
    page.wait_for_timeout(1200)
    assert all(not r["off"] for r in legend(page)), f"[{name}] final empty click should clear focus"
    print(f"[{name}] ok: sorted legend, label click, drill-down={drilled}, pop")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:6969")
    args = ap.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=EXE)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(f"{args.base}/map")
        page.wait_for_selector("canvas")
        assert page.eval_on_selector("canvas", "e => e.dataset.intro") == "1", (
            "intro should run on hard load"
        )
        page.click("text=inbox")
        page.wait_for_timeout(300)
        page.click("text=map")
        page.wait_for_selector("canvas")
        assert page.eval_on_selector("canvas", "e => e.dataset.intro") is None, (
            "intro must not replay on SPA navigation"
        )
        run(page, args.base, "", "3d")
        run(page, args.base, "#2d", "2d")
        browser.close()
    print("smoke passed")


if __name__ == "__main__":
    sys.exit(main())
