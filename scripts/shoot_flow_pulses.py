"""Headless verification + screenshot checkpoint for the flow pulses (feature A).

Shader linking happens at runtime, so tsc, the linter and the unit suite can
all pass a program the GPU refuses — that is exactly how #116 shipped a broken
map for one commit. This drives the real bundle, fails loudly on any console
error, and archives a frame per the checkpoint convention.

It also proves the pulse is actually travelling rather than merely present:
two frames a beat apart must differ, and with the clock pinned they must not.

Usage: uv run --with playwright python scripts/shoot_flow_pulses.py --url http://127.0.0.1:6973
"""

import argparse
import hashlib
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "03-flow-pulses"
SETTLE_MS = 6500

# The web only draws as dim approaches volume, so 2D overview shows no strands.
#
# Matched exactly, not by substring. An earlier version used a regex over the
# button text and also matched the legend entry "3d/vfx & motion-design craft",
# which set a focus — and focus starts the point shader's own pulse. Frames then
# differed for a reason that had nothing to do with the flow pulses, and the
# check passed while proving nothing.
SHOW_WEB_JS = """
() => {
  const wanted = new Set(['web']);
  const hit = [...document.querySelectorAll('button,[role=button],label')]
    .filter(el => wanted.has((el.textContent || '').trim().toLowerCase()));
  hit.forEach(el => el.click());
  return hit.map(el => (el.textContent || '').trim());
}
"""


def shoot(page, path: Path) -> str:
    page.locator("canvas").screenshot(path=str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def arm(browser, url: str, motion: bool, tag: str) -> tuple[str, str, list[str]]:
    """Settle the web view, then two frames a beat apart. No focus is set."""
    errors: list[str] = []
    ctx = browser.new_context(
        viewport={"width": 1600, "height": 1000},
        reduced_motion="no-preference" if motion else "reduce",
    )
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"PAGEERROR {str(e)[:200]}"))
    suffix = "?motion=on" if motion else ""
    page.goto(f"{url}/map{suffix}", wait_until="networkidle")
    page.wait_for_selector("canvas", timeout=30_000)
    page.wait_for_timeout(SETTLE_MS)
    print(f"  toggled: {page.evaluate(SHOW_WEB_JS)}")
    page.wait_for_timeout(4000)  # let webT and the camera finish easing

    a = shoot(page, OUT / f"05-{tag}-a.png")
    page.wait_for_timeout(700)  # ~half a pulse at SPEED 4.5
    b = shoot(page, OUT / f"05-{tag}-b.png")
    ctx.close()
    return a, b, errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        print("motion on:")
        on_a, on_b, on_err = arm(browser, args.url, True, "motion-on")
        print("motion reduced:")
        off_a, off_b, off_err = arm(browser, args.url, False, "motion-off")
        browser.close()

    errors = on_err + off_err
    print(f"\n  motion on       {on_a} / {on_b}  -> {'differ' if on_a != on_b else 'IDENTICAL'}")
    print(f"  motion reduced  {off_a} / {off_b}  -> {'DIFFER' if off_a != off_b else 'identical'}")
    if errors:
        print("\nconsole errors:")
        for e in errors[:8]:
            print(f"  {e}")

    # Both arms are needed. "Frames differ" alone proves nothing — a still-easing
    # camera or a focus pulse would do that too. The pulse is only demonstrated
    # if motion changes things AND pinning the clock stops them changing.
    if errors:
        raise SystemExit("console errors present")
    if on_a == on_b:
        raise SystemExit("motion on: frames identical — the pulse is not animating")
    if off_a != off_b:
        raise SystemExit("motion reduced: frames differ — something else is animating")
    print("\nthe travelling pulse is the only thing moving")


if __name__ == "__main__":
    main()
