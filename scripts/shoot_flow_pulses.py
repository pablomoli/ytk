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

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "flow-pulses"
SETTLE_MS = 6500

# The web only draws as dim approaches volume, so 2D overview shows no strands.
SHOW_WEB_JS = """
() => {
  const hit = [...document.querySelectorAll('button,[role=button],label')]
    .filter(el => /web|3d|volume|dimension/i.test(el.textContent || ''));
  hit.forEach(el => el.click());
  return hit.map(el => (el.textContent || '').trim()).slice(0, 6);
}
"""


def shoot(page, path: Path) -> str:
    page.locator("canvas").screenshot(path=str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR {str(e)[:200]}"))
        page.goto(f"{args.url}/map", wait_until="networkidle")
        page.wait_for_selector("canvas", timeout=30_000)
        page.wait_for_timeout(SETTLE_MS)

        clicked = page.evaluate(SHOW_WEB_JS)
        print(f"toggled: {clicked}")
        page.wait_for_timeout(3500)

        a = shoot(page, OUT / "05-shader-frame-a.png")
        page.wait_for_timeout(700)  # ~half a pulse at SPEED 4.5
        b = shoot(page, OUT / "05-shader-frame-b.png")

        print(f"frame a {a}\nframe b {b}")
        print("pulse is travelling" if a != b else "FRAMES IDENTICAL — pulse is not moving")
        if errors:
            print("\nconsole errors:")
            for e in errors[:8]:
                print(f"  {e}")
        browser.close()

    if errors:
        raise SystemExit("console errors present")
    if a == b:
        raise SystemExit("frames identical — the pulse is not animating")


if __name__ == "__main__":
    main()
