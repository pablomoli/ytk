# UI/UX Polish Sprint — Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement these plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Source spec: `docs/uiux-polish-sprint.md` (committed, canonical). Scout rationale lives in the
two scout reports referenced there. Execute plans strictly in order — later phases consume
interfaces earlier phases create.

| Plan file | Phase | Depends on |
|---|---|---|
| `phase-0-statics.md` | Statics and fixes (no dependencies) | — |
| `phase-1-motion-foundation.md` | GSAP install, motion.ts, Flip masonry, viewer morph + dither reveal | Phase 0 (NoteViewer) |
| `phase-2-typography.md` | SplitHeading, ScrambleStatus, hover decode, CountUp, ScrollReveal | Phase 1 (motion.ts) |
| `phase-3-surface-reveals.md` | Thumbnail dissolve, PixelBloom hover, TargetCursor | Phase 1 (motion.ts, bayer.ts, PixelDissolve) |
| `phase-4-viz-map-grove.md` | Map inertial pan/eased zoom, grove postprocessing | — (independent of 1-3) |
| `phase-5-viz-growth-transitions.md` | Growth composer refactor, pixelate swap transitions | Phase 4 (postprocessing installed, grain.ts) |

## Global constraints (apply to every task in every phase)

- Stack: React 19 + TypeScript, TanStack Router/Query/Virtual, plain three.js ^0.185.1, Vite+ (`vp` CLI). Package manager operations go through `vp` (`vp add <pkg>`, never `pnpm add`/`npm i`). All `vp` commands run from `/Users/melocoton/Developer/ytk/web/`.
- Styling: hand-written CSS in `web/src/styles.css` + tokens in `web/src/theme.css`. NO Tailwind, no CSS-in-JS, no new component libraries. Use custom properties: `--bg0 #0e0e10`, `--bg1 #161618`, `--bg2 #1c1c1f`, `--bg3 #26262a`, `--ink #f0eee7`, `--ink2 #b7b5aa`, `--mute #83817a`, `--line rgba(255,255,255,.08)`, `--accent #e2b04a`, `--live #4ade80`, `--r 10px`, `--ease cubic-bezier(.25,.1,.25,1)`.
- Typeface: Newsreader only. Never introduce a sans or mono family. No uppercase labels (lowercase transform is the house style). No emojis anywhere.
- Motion registers: 180ms house transitions; 300ms morphs; 400ms wipes; 600ms staggered reveals. Never springy/bouncy eases. Every JS-driven animation must no-op under `prefers-reduced-motion: reduce` (the CSS kill-switch in theme.css:86-88 cannot stop GSAP/canvas animation — guard in JS).
- Dependencies: the ONLY packages any phase may add are `gsap` (Phase 1) and `postprocessing` (Phase 4). Everything else is owned code.
- Identity surfaces (`/growth`, `/grove`, `/map` rendering internals) are augmented, never replaced. The reaction-diffusion sim, tree topology, and UMAP math are untouched. `/growth` keeps exactly one dither layer (documented at `web/src/lib/growth/shaders.ts:197`).
- Tests: vitest through `vp test` (run in `web/`). Test files are colocated (`Foo.test.tsx` next to `Foo.tsx`) and import from `vitest` (matching existing tests, e.g. `web/src/components/Skeletons.test.tsx`).
- Type/lint gate: `vp check` (runs fmt + lint + tsc) must pass before every commit. Note: `web/src/lib/growth/` has PRE-EXISTING broken test files (`dna.test.ts`, `palette.test.ts`, `topology.test.ts`, `events.test.ts`, `philosophy.test.ts`, `layout.test.ts` reference deleted modules). If `vp check`/`vp test` fails ONLY in those pre-existing files, that is not caused by your change — report it and proceed; do not fix or delete them unless a task says to.
- Commits: one per task, message style `feat(web): ...` / `fix(web): ...`, ending with the trailer line `Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY`. Never add any author/contributor besides the repo user.
- The dev hub runs at `http://localhost:6969` (launchd service serving the INSTALLED bundle — it does NOT pick up source edits). For visual verification use the Vite dev server: `cd web && vp dev --port 5173` and screenshot `http://localhost:5173/<route>` headlessly (never open a visible browser window).

## Headless screenshot harness (used by every phase's verification)

Write this once to the scratchpad and reuse (`SHOT=<script> URL=<url> OUT=<png> [WAIT=ms]`):

```python
# shot.py — usage: uv run --with playwright python shot.py <url> <out.png> [wait_ms] [reduced]
import sys
from playwright.sync_api import sync_playwright

url, out = sys.argv[1], sys.argv[2]
wait = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
reduced = len(sys.argv) > 4 and sys.argv[4] == "reduced"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    if reduced:
        page.emulate_media(reduced_motion="reduce")
    page.goto(url)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(wait)
    page.screenshot(path=out)
    browser.close()
print(out)
```

Reduced-motion gate (every phase): re-run the phase's screenshots with the `reduced` flag; any
mid-transition capture must equal the settled state (animations must not exist under reduced motion).
