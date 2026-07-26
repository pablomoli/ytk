"""Live masonry stability probe (#22).

The hermetic guard lives in web/src/components/MasonryGrid.test.tsx and counts
layout passes. It cannot count style writes in a synthetic DOM, because it emits no attribute
mutation when a style property is set to the value it already holds — the
pre-fix component passes a write-counting assertion cleanly there. A real
browser does record those writes, so this is where that half of the guard runs.

Not part of the unit suite on purpose: it needs a browser and a running hub
(#114 — the unit suite must never launch one).

    uv run python scripts/probe_masonry.py                    # against the hub
    uv run python scripts/probe_masonry.py http://localhost:5174

Measured on the pre-fix bundle, 60 cards: one card click produced 1286 style
writes, five clicks produced 6430. Both are 0 once the grid only relayouts on
structural change.
"""

import sys

from playwright.sync_api import sync_playwright

OBSERVE = """() => {
  window.__writes = 0;
  window.__obs = new MutationObserver(muts => { window.__writes += muts.length; });
  document.querySelectorAll('.masonry > *').forEach(el => {
    window.__obs.observe(el, { attributes: true, attributeFilter: ['style'] });
  });
  return document.querySelectorAll('.masonry > *').length;
}"""

READ = "() => window.__writes"
RESET = "() => { window.__writes = 0; }"


def probe(base: str) -> int:
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1512, "height": 900})
        page.goto(f"{base}/inbox", wait_until="domcontentloaded")
        page.wait_for_selector(".masonry > .card", timeout=30000)
        page.wait_for_timeout(4000)  # let first paint and image decodes settle

        n = page.evaluate(OBSERVE)
        print(f"observing {n} cards at {base}")

        page.evaluate(RESET)
        page.wait_for_timeout(6000)
        idle = page.evaluate(READ)
        print(f"  idle, 6s, untouched          : {idle:5d}")
        if idle:
            failures.append(f"grid rewrote itself {idle}x with no interaction")

        cards = page.query_selector_all(".masonry > .card")
        page.evaluate(RESET)
        for i in range(5):
            cards[min(i, len(cards) - 1)].click(force=True)
            page.wait_for_timeout(250)
        clicks = page.evaluate(READ)
        print(f"  five card clicks             : {clicks:5d}")
        if clicks:
            # Selection is an outline-color change and cannot move a card.
            failures.append(f"selecting cards rewrote geometry {clicks}x")

        page.evaluate(RESET)
        page.set_viewport_size({"width": 1100, "height": 900})
        page.wait_for_timeout(1200)
        resize = page.evaluate(READ)
        print(f"  viewport resize              : {resize:5d}")
        if not resize:
            # The control: proves the grid still lays out at all.
            failures.append("resize produced no relayout — the grid is inert")

        browser.close()

    for f in failures:
        print(f"FAIL: {f}")
    if not failures:
        print("PASS: geometry is written only when it changes")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(probe(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:6969"))
