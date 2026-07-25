"""Geometry gate for the inbox rail (#125).

jsdom reports every rect as zero, so the unit suite cannot see this class of
bug at all — the sibling #124 defect escaped its unit test for exactly that
reason. This asserts the two things the issue actually promises: the rail
never runs past the fold, and the ingest action is genuinely clickable.

Not part of the pytest suite on purpose: it needs a browser and a running
hub, and tests/conftest.py fails any test that reaches Playwright (#114).

Run: uv run python scripts/probe_inbox_rail.py [--base http://127.0.0.1:6969]
"""

import argparse
import sys

from playwright.sync_api import sync_playwright

VIEWPORTS = [(1440, 900), (1280, 800), (1280, 700), (1152, 620), (1024, 576)]

PROBE = """
() => {
  const rail = document.querySelector('.rail');
  const btns = [...rail.querySelectorAll('button')];
  const ingest = btns.find((b) => b.textContent.trim() === 'ingest');
  const r = rail.getBoundingClientRect();
  const ir = ingest ? ingest.getBoundingClientRect() : null;
  let hittable = false;
  if (ir && ir.width && ir.height) {
    const cx = ir.left + ir.width / 2;
    const cy = ir.top + ir.height / 2;
    if (cy >= 0 && cy <= innerHeight && cx >= 0 && cx <= innerWidth) {
      const hit = document.elementFromPoint(cx, cy);
      hittable = hit === ingest || (hit && ingest.contains(hit));
    }
  }
  return {
    railBottomPastFold: Math.round(r.bottom - innerHeight),
    ingestFound: !!ingest,
    ingestHittable: hittable,
  };
}
"""


def check(page, label: str, failures: list[str]) -> None:
    m = page.evaluate(PROBE)
    ok = m["ingestFound"] and m["ingestHittable"] and m["railBottomPastFold"] <= 0
    print(
        f"  {'PASS' if ok else 'FAIL'} {label}: "
        f"railBottomPastFold={m['railBottomPastFold']} "
        f"ingestHittable={m['ingestHittable']}"
    )
    if not ok:
        failures.append(label)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:6969")
    args = ap.parse_args()
    url = f"{args.base}/inbox"

    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for reduced in (False, True):
            motion = "reduce" if reduced else "no-preference"
            for width, height in VIEWPORTS:
                ctx = browser.new_context(
                    viewport={"width": width, "height": height},
                    reduced_motion=motion,
                )
                page = ctx.new_page()
                page.goto(url)
                page.wait_for_selector(".rail", timeout=20000)
                page.wait_for_timeout(2000)
                check(page, f"{width}x{height} motion={motion}", failures)
                page.evaluate("window.scrollTo(0, 400)")
                page.wait_for_timeout(300)
                check(page, f"{width}x{height} motion={motion} scrolled", failures)
                ctx.close()
        browser.close()
    if failures:
        print(f"\nFAILED {len(failures)} check(s): {failures}")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
