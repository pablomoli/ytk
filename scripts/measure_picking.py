"""Measure #101's two fixes in a real browser, headless.

The figures in docs/assets/02-picking/ 01-03 are models. This one is not: it
drives the actual bundle and records what the map does at rest and under the
cursor. Writes docs/assets/02-picking/measured.json, which fig04 renders.

Two hub instances are started on scratch ports so the user's own hub on 6969
is never touched: one from this worktree (the fixes) and one from a checkout
that predates them (the baseline).

Usage:
  uv run --with playwright python scripts/measure_picking.py \
      --before-url http://127.0.0.1:6972 --after-url http://127.0.0.1:6971
"""

import argparse
import json
import statistics
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "02-picking" / "measured.json"

IDLE_SECONDS = 4.0
HOVER_EVENTS = 400
SETTLE_MS = 6000

# Counts the *app's* rAF callbacks, which is the only number that answers
# "is the loop parked". Installed before the bundle runs, so every scheduling
# call the renderer makes passes through the wrapper.
#
# An earlier version drove its own rAF loop and counted its own frames. That
# measures display headroom, not the app: it reported the fixed build at 120fps
# and the baseline at 60, i.e. exactly backwards, because a parked app leaves
# the display free to run fast. Never count your own callbacks.
#
# It also has to attribute them. A bare total is confounded: React's scheduler
# runs its own rAF loop on this page, and when the map parks, React simply gets
# the frames the map used to take — so the total barely moves while the map's
# own loop has gone to zero. Bucketing by call site separates the two.
INSTRUMENT_JS = """
window.__raf = 0;
window.__rafBy = {};
const __origRaf = window.requestAnimationFrame.bind(window);
window.requestAnimationFrame = (cb) => {
  window.__raf++;
  const st = (new Error()).stack || '';
  const parts = st.split('\\n');
  const line = (parts[2] || parts[1] || 'unknown').trim().slice(0, 130);
  window.__rafBy[line] = (window.__rafBy[line] || 0) + 1;
  return __origRaf(cb);
};
"""

# The React vendor chunk. Identified empirically: these call sites appear in
# both builds at identical offsets, and they are the only ones still scheduling
# once the map's loop parks. Everything else is the renderer.
VENDOR = ":9:"

# setTimeout, deliberately: a rAF-based wait would schedule frames of its own
# and contaminate the count it is trying to read.
IDLE_JS = """
(seconds) => new Promise((resolve) => {
  window.__rafBy = {};
  const start = window.__raf;
  const t0 = performance.now();
  setTimeout(() => resolve({
    frames: window.__raf - start,
    elapsed: performance.now() - t0,
    by: window.__rafBy,
  }), seconds * 1000);
})
"""

# mousemove listeners run synchronously inside dispatchEvent, so timing the
# dispatch captures the hover handler itself — the linear scan before, the
# block read after — without needing a profiler.
HOVER_JS = """
(n) => {
  const canvas = document.querySelector('canvas');
  if (!canvas) return null;
  const r = canvas.getBoundingClientRect();
  const samples = [];
  for (let i = 0; i < n; i++) {
    const x = r.left + (0.15 + 0.7 * ((i * 97) % 100) / 100) * r.width;
    const y = r.top + (0.15 + 0.7 * ((i * 61) % 100) / 100) * r.height;
    const ev = new MouseEvent('mousemove', {
      clientX: x, clientY: y, bubbles: true, view: window,
    });
    const t0 = performance.now();
    window.dispatchEvent(ev);
    samples.push(performance.now() - t0);
  }
  samples.sort((a, b) => a - b);
  return { median: samples[Math.floor(samples.length / 2)], n: samples.length };
}
"""


def probe(page, url: str, label: str) -> dict:
    print(f"  {label}: {url}")
    page.add_init_script(INSTRUMENT_JS)
    page.goto(f"{url}/map", wait_until="networkidle")
    page.wait_for_selector("canvas", timeout=30_000)
    # Let the intro easing, focus ramp and any fly-to finish; the idle number
    # is meaningless while those are still running.
    page.wait_for_timeout(SETTLE_MS)

    idle = page.evaluate(IDLE_JS, IDLE_SECONDS)
    seconds = idle["elapsed"] / 1000
    by = idle["by"] or {}
    renderer = sum(v for k, v in by.items() if VENDOR not in k)
    vendor = sum(v for k, v in by.items() if VENDOR in k)
    fps = renderer / seconds
    print(
        f"    idle: render loop {renderer} calls -> {fps:.1f}/s   "
        f"(React scheduler {vendor}, total {idle['frames']})"
    )

    hover = page.evaluate(HOVER_JS, HOVER_EVENTS)
    if hover is None:
        raise SystemExit(f"{label}: no canvas found")
    print(f"    hover: median {hover['median']:.4f} ms over {hover['n']} events")
    return {
        "idle_fps": round(fps, 2),
        "vendor_fps": round(vendor / seconds, 2),
        "hover_ms": round(hover["median"], 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before-url", required=True)
    ap.add_argument("--after-url", required=True)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    before_runs: list[dict] = []
    after_runs: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for run in range(args.runs):
                print(f"run {run + 1}/{args.runs}")
                for url, label, sink in (
                    (args.before_url, "before", before_runs),
                    (args.after_url, "after", after_runs),
                ):
                    page = browser.new_page(viewport={"width": 1600, "height": 1000})
                    try:
                        sink.append(probe(page, url, label))
                    finally:
                        page.close()
            agent = browser.new_page().evaluate("() => navigator.userAgent")
        finally:
            browser.close()

    def median_of(runs: list[dict], key: str) -> float:
        return round(statistics.median(r[key] for r in runs), 4)

    payload = {
        "runs": args.runs,
        "idle_seconds": IDLE_SECONDS,
        "hover_events": HOVER_EVENTS,
        "agent": "headless chromium",
        "user_agent": agent,
        "before": {
            "idle_fps": median_of(before_runs, "idle_fps"),
            "hover_ms": median_of(before_runs, "hover_ms"),
            "runs": before_runs,
        },
        "after": {
            "idle_fps": median_of(after_runs, "idle_fps"),
            "hover_ms": median_of(after_runs, "hover_ms"),
            "runs": after_runs,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote {OUT}")
    print(
        f"  idle  {payload['before']['idle_fps']} -> {payload['after']['idle_fps']} fps\n"
        f"  hover {payload['before']['hover_ms']} -> {payload['after']['hover_ms']} ms"
    )


if __name__ == "__main__":
    main()
