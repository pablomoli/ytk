"""Capture the same frame with and without bloom, from the same build.

The pair is what makes the checkpoint a validation rather than a before/after:
run the notebook's numpy pipeline over the un-bloomed capture and the result
should match what the GPU produced. If it does not, either the notebook is
lying about the shader or the shader is not doing what the notebook models.

Usage: uv run --with playwright python scripts/shoot_bloom_pair.py --url http://127.0.0.1:6973
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "05-bloom"
SETTLE_MS = 6500

SHOW_WEB_JS = """
() => {
  const wanted = new Set(['web']);
  const hit = [...document.querySelectorAll('button,[role=button],label')]
    .filter(el => wanted.has((el.textContent || '').trim().toLowerCase()));
  hit.forEach(el => el.click());
  return hit.map(el => (el.textContent || '').trim());
}
"""

# Everything except the canvas is hidden before the shot. Playwright's element
# screenshot captures the composited page clipped to the element, so the nav,
# legend and control chips sitting on top of the canvas end up in the image —
# and the first run of this checkpoint duly "found" a 68% error that was
# entirely the numpy model blooming DOM the shader cannot see.
HIDE_UI_JS = """
() => {
  const canvas = document.querySelector('canvas');
  let hidden = 0;
  document.querySelectorAll('body *').forEach(el => {
    if (el === canvas || el.contains(canvas) || canvas.contains(el)) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    el.style.visibility = 'hidden';
    hidden++;
  });
  return hidden;
}
"""


def capture(browser, url: str, query: str, out: Path) -> list[str]:
    errors: list[str] = []
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, reduced_motion="reduce")
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"PAGEERROR {str(e)[:200]}"))
    page.goto(f"{url}/map{query}", wait_until="networkidle")
    page.wait_for_selector("canvas", timeout=30_000)
    page.wait_for_timeout(SETTLE_MS)
    page.evaluate(SHOW_WEB_JS)
    page.wait_for_timeout(4000)
    hidden = page.evaluate(HIDE_UI_JS)
    page.wait_for_timeout(600)
    OUT.mkdir(parents=True, exist_ok=True)
    page.locator("canvas").screenshot(path=str(out))
    print(f"    hid {hidden} overlay elements")
    print(f"  {out.name}  <- {query or '(default)'}")
    ctx.close()
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Motion pinned in both so the only difference between the two frames
        # is the bloom chain — a travelling pulse would otherwise move between
        # captures and the comparison would be measuring the wrong thing.
        errs = capture(browser, args.url, "?bloom=off", OUT / "scene-raw.png")
        errs += capture(browser, args.url, "", OUT / "scene-bloomed.png")
        browser.close()

    if errs:
        for e in errs[:8]:
            print(f"  ERROR {e}")
        raise SystemExit("console errors present")
    print("captured the pair")


if __name__ == "__main__":
    main()
