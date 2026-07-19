# Phase 5 — Viz Track B: Growth Compositor + Pixelate Transitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the growth workbench's multi-region render through an offscreen target so a compositor pass (vignette + seeded grain + SMAA) can filter it — with a hard pixel-identical gate on the refactor commit — and give growth's theme/variant switches a Bayer-flavored pixelate wipe.

**Architecture:** Two independent tracks. (A) `web/src/lib/growth/scene.ts` currently scissors each region (`drawRegion`, lines 371-383) straight into the default framebuffer; the refactor redirects those exact draws into one canvas-sized `WebGLRenderTarget`, then composites to screen — first with a bare copy (commit 1, must be pixel-identical), then with the effect pass (commit 2, user-reviewed). (B) `web/src/lib/pixelateSwap.ts` is a renderer-agnostic 2D transition: snapshot the canvas, run the swap, then dissolve the snapshot overlay through descending pixelation. **Scope decision recorded:** the sprint doc named vendored gl-transitions GLSL; this plan ships the 2D pixelate overlay instead — it works uniformly over WebGL and 2D canvases without threading textures through three different rendering systems, is deterministic, and speaks the same blocky dialect. The GLSL route stays open as a later upgrade; say this in the commit body.

**Tech Stack:** `postprocessing` (installed in Phase 4), `web/src/lib/grain.ts` (Phase 4), canvas 2D.

**Identity rules (non-negotiable):** The reaction-diffusion simulation, its shaders, topology, and DNA math are untouched. The one-device-pixel dither rule (`web/src/lib/growth/shaders.ts:197`) stands — the compositor adds NO second dither layer (grain is additive noise on the composite, not a quantization dither; intensity stays a whisper).

## Global Constraints

See `docs/plans/uiux-polish/README.md`. Phase-specific:
- Commit 1 of the refactor has a HARD acceptance gate: screenshots before/after must be byte-comparable (pixel diff = 0) at fixed seed and viewport. Do not proceed to commit 2 until the gate passes.
- `preserveDrawingBuffer: true` (scene.ts line 143) must keep working — `snapshot()` (line 491) reads the canvas via drawImage.

---

### Task 1: Growth render-target refactor (pixel-identical commit)

**Files:**
- Modify: `web/src/lib/growth/scene.ts`

Current facts (verified): renderer at lines 138-145; display draw path is `drawRegion(slot, region, height, pulse)` at 371-383 which sets viewport+scissor then `renderer.render(displayScene, camera)`; the frame loop calls it at 424-428 inside `setScissorTest(true)`; `resize()` at 363-369; `destroy()` at 508-519.

- [ ] **Step 1: Baseline screenshots (BEFORE any edit)** — dev server on `/growth`, fixed viewport 1600x1000, dsf 2. The sim is live/animated, so pixel-identity needs a frozen state: click `pause` first (HubControls has a pause chip — Playwright `page.click('text=pause')`), wait 500ms, screenshot to `scratchpad/growth-before.png`. Keep the browser session OPEN (pausing freezes the sim state; a reload would regrow differently since events replay against a live clock).

Because holding one session across an edit+rebuild is fragile, use this deterministic alternative if the diff proves noisy: capture with the page's sim paused immediately (`page.click` on pause as soon as the gallery loads), which pins the freshly-seeded state — that state IS reproducible across reloads for the same theme because seeding is content-derived (`makeSeedTexture` from topology; `randomFrom` is seed-hashed, no Date/Math.random). Two paused fresh loads of the same theme must produce identical dishes; verify that FIRST (two before-shots, diff=0) — if they differ, stop and report; do not attempt the refactor gate against a nondeterministic baseline.

- [ ] **Step 2: Redirect the region draws** — in `scene.ts`:

Add to the three imports from 'three': `LinearFilter` is already imported; append `WebGLRenderTarget` is already imported (line 17) — nothing to add.

After the `displayScene.add(...)` line (197), add:

```ts
/* Offscreen composite target: drawRegion renders every dish into this
   texture (same viewports/scissors, now in texture space), and a final
   pass puts it on screen. Commit 1 = bare copy, pixel-identical. */
let composite = new WebGLRenderTarget(2, 2, { depthBuffer: false, stencilBuffer: false })
composite.texture.minFilter = LinearFilter
composite.texture.magFilter = LinearFilter
```

In `resize()` (lines 363-369), after `renderer.setSize(width, height, false)` add:

```ts
const dpr = Math.min(devicePixelRatio || 1, 2)
composite.setSize(Math.max(2, Math.round(width * dpr)), Math.max(2, Math.round(height * dpr)))
```

In `drawRegion` (371-383): the viewport/scissor calls use CSS-pixel region coords; when rendering into a target, three.js does NOT apply the renderer's pixelRatio — multiply manually. Replace the tail of `drawRegion` (from `const glY = ...`):

```ts
const dpr = Math.min(devicePixelRatio || 1, 2)
const glY = (height - (region.y + region.h)) * dpr
renderer.setRenderTarget(composite)
renderer.setViewport(region.x * dpr, glY, region.w * dpr, region.h * dpr)
renderer.setScissor(region.x * dpr, glY, region.w * dpr, region.h * dpr)
renderer.render(displayScene, camera)
renderer.setRenderTarget(null)
```

In the frame loop (424-428), after the tile draws and `setScissorTest(false)`, blit the composite to screen. Add ONE more tiny fullscreen scene near the display scene setup:

```ts
import { MeshBasicMaterial } from 'three'   // add to the three import list
...
const blitScene = new Scene()
const blitMaterial = new MeshBasicMaterial({ map: composite.texture })
blitScene.add(new Mesh(geometry, blitMaterial))
```

and in the loop replace the region-draw block:

```ts
const height = canvas.clientHeight || innerHeight
renderer.setScissorTest(true)
drawRegion(stage, regions.stage, height, pulse)
tiles.forEach((tile, i) => drawRegion(tile, regions.mutations[i], height, pulse))
renderer.setScissorTest(false)
blitMaterial.map = composite.texture
renderer.render(blitScene, camera)
```

Two traps the executor must handle:
1. `setScissorTest(true)` applies to target renders too — keep it exactly around the drawRegion calls as today, and make sure the final blit runs AFTER `setScissorTest(false)` with a full-canvas viewport: add `renderer.setViewport(0, 0, canvas.width, canvas.height)` before the blit render.
2. Clearing: today each frame draws regions over the previous frame's default framebuffer with `setClearColor(0x050607)`. The composite target needs the same base: before the drawRegion calls add `renderer.setRenderTarget(composite); renderer.setClearColor(0x050607, 1); renderer.clear(); renderer.setRenderTarget(null)`.
3. `resize()` runs before the first frame (line 432) — composite is sized before use.

In `destroy()` add `composite.dispose(); blitMaterial.dispose()`.

- [ ] **Step 3: The gate** — rebuild (`vp dev` hot-reloads), fresh load `/growth`, pause immediately, screenshot to `scratchpad/growth-after.png`. Diff:

```bash
uv run --with pillow --with numpy python -c "
from PIL import Image; import numpy as np
a = np.asarray(Image.open('growth-before.png'), dtype=int); b = np.asarray(Image.open('growth-after.png'), dtype=int)
print('shape', a.shape == b.shape, 'maxdiff', int(np.abs(a-b).max()), 'pixels-off', int((np.abs(a-b).sum(axis=-1) > 0).sum()))
"
```

Expected: `maxdiff 0`. Allow up to maxdiff 1 on <0.1% of pixels ONLY if traced to float rounding in the dpr multiply — investigate before accepting; the goal is 0.

- [ ] **Step 4: Gate `vp check`** and commit (commit 1):

```bash
git add web/src/lib/growth/scene.ts
git commit -m "refactor(web): growth regions render through an offscreen composite target

Pixel-identical by screenshot diff at fixed seed and paused sim; the
compositor pass lands separately.

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 2: Growth effect pass (restraint tier)

**Files:**
- Modify: `web/src/lib/growth/scene.ts`

- [ ] **Step 1: Swap the bare blit for a composer** — imports:

```ts
import { EffectComposer, EffectPass, SMAAEffect, TexturePass, VignetteEffect } from 'postprocessing'
import { SeededGrainEffect } from '../grain'
```

Replace the blitScene/blitMaterial setup from Task 1 with:

```ts
/* Restraint tier only: vignette + static seeded grain + SMAA. No tone
   mapping (the palette ramp is already authored), and NO second dither —
   the one-device-pixel rule in shaders.ts stands. */
const composer = new EffectComposer(renderer)
const texturePass = new TexturePass(composite.texture)
composer.addPass(texturePass)
composer.addPass(new EffectPass(camera, new SMAAEffect(), new VignetteEffect({ offset: 0.32, darkness: 0.5 }), new SeededGrainEffect(0.04)))
```

In `resize()`, after the composite.setSize line, add `composer.setSize(width, height)`. In the frame loop, the blit block becomes:

```ts
renderer.setViewport(0, 0, canvas.width, canvas.height)
texturePass.texture = composite.texture
composer.render()
```

In `destroy()`: `composer.dispose()` (replaces blitMaterial.dispose()).

- [ ] **Step 2: Verify** — `vp check` clean. Screenshot pair (paused, fixed seed): the after shows gently darkened dish edges, AA on rim hairlines, whisper grain in the dark field. Post both to the user for taste sign-off — vignette/grain settings are theirs to tune (0.04 grain, 0.5 darkness are starting values).

- [ ] **Step 3: `snapshot()` sanity** — the thumbnail path (line 491, canvas drawImage crop) reads the on-screen canvas, which now holds the composed output — thumbnails inherit the finish. Verify one gallery chip thumbnail still renders (screenshot the gallery strip).

- [ ] **Step 4: Commit (commit 2)**

```bash
git add web/src/lib/growth/scene.ts
git commit -m "feat(web): growth compositor — SMAA, vignette, seeded grain over the composite

No tone mapping, no second dither: the shaders' one-device-pixel rule
stands. Intensities are starting values pending taste review.

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 3: pixelateSwap transition helper

**Files:**
- Create: `web/src/lib/pixelateSwap.ts`
- Create: `web/src/lib/pixelateSwap.test.ts`

**Interfaces (Produces):**

```ts
export function pixelateSwap(canvas: HTMLCanvasElement, swap: () => void, opts?: { duration?: number }): void
// Snapshot the canvas into an overlay <canvas> positioned over it, call
// swap() (which changes what the source canvas shows), then dissolve the
// overlay: pixelation coarsens 1x -> 32x block size while opacity falls,
// on the house ease timing (default duration = DUR.wipe). Reduced motion
// or a 0-sized canvas: swap() runs, no overlay. Re-entrant calls replace
// the previous overlay immediately.
```

Scope decision (recorded in the plan header): 2D overlay pixelate instead of vendored GLSL — uniform across WebGL/2D canvases, deterministic, no texture plumbing.

- [ ] **Step 1: Failing test** — `web/src/lib/pixelateSwap.test.ts`:

```ts
import { expect, test, vi } from 'vitest'
import { pixelateSwap } from './pixelateSwap'

test('swap always runs; degraded environments get no overlay', () => {
  // jsdom canvas has no real 2d context data, width/height 0 -> degraded path
  const canvas = document.createElement('canvas')
  document.body.appendChild(canvas)
  const swap = vi.fn()
  pixelateSwap(canvas, swap)
  expect(swap).toHaveBeenCalledTimes(1)
  expect(document.querySelector('.pixelate-overlay')).toBeNull()
})
```

- [ ] **Step 2: Verify failure**, then implement `web/src/lib/pixelateSwap.ts`:

```ts
import { DUR, reducedMotion } from './motion'

/* Pixelate wipe between two states of a canvas surface: freeze the old
   frame in an overlay, let the caller swap the live canvas, then dissolve
   the frozen frame through coarsening pixel blocks. The blocky dialect of
   the growth dither, applied to state changes. */
let active: HTMLCanvasElement | null = null

export function pixelateSwap(canvas: HTMLCanvasElement, swap: () => void, opts?: { duration?: number }): void {
  const duration = (opts?.duration ?? DUR.wipe) * 1000
  const w = canvas.width
  const h = canvas.height
  if (reducedMotion() || !w || !h || !canvas.parentElement) { swap(); return }

  active?.remove()
  const overlay = document.createElement('canvas')
  overlay.className = 'pixelate-overlay'
  overlay.width = w
  overlay.height = h
  const rect = canvas.getBoundingClientRect()
  const host = canvas.parentElement
  Object.assign(overlay.style, {
    position: 'absolute',
    left: `${canvas.offsetLeft}px`,
    top: `${canvas.offsetTop}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    pointerEvents: 'none',
    imageRendering: 'pixelated',
  })
  const context = overlay.getContext('2d')
  if (!context) { swap(); return }
  try { context.drawImage(canvas, 0, 0) } catch { swap(); return }
  const frame = document.createElement('canvas') // untouched copy of the old state
  frame.width = w; frame.height = h
  frame.getContext('2d')?.drawImage(overlay, 0, 0)
  host.appendChild(overlay)
  active = overlay

  swap()

  const start = performance.now()
  const step = (now: number) => {
    if (active !== overlay) return
    const t = Math.min(1, (now - start) / duration)
    const eased = 0.5 - 0.5 * Math.cos(t * Math.PI) // house-adjacent, dependency-free
    const block = 1 + eased * 31
    const dw = Math.max(1, Math.round(w / block))
    const dh = Math.max(1, Math.round(h / block))
    context.imageSmoothingEnabled = false
    context.clearRect(0, 0, w, h)
    context.drawImage(frame, 0, 0, dw, dh)         // downsample
    context.drawImage(overlay, 0, 0, dw, dh, 0, 0, w, h) // upscale blocky
    overlay.style.opacity = `${1 - eased}`
    if (t < 1) requestAnimationFrame(step)
    else { overlay.remove(); if (active === overlay) active = null }
  }
  requestAnimationFrame(step)
}
```

(The double drawImage trick pixelates in-place: shrink the frozen frame into the overlay's top-left, then stretch that region back over the full overlay with smoothing off.)

- [ ] **Step 3: Verify** — `vp test src/lib/pixelateSwap.test.ts` → PASS; `vp check` clean.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/pixelateSwap.ts web/src/lib/pixelateSwap.test.ts
git commit -m "feat(web): pixelateSwap — blocky dissolve between canvas states

2D overlay pixelation instead of vendored gl-transitions GLSL: uniform
across WebGL and 2D canvases with zero texture plumbing; GLSL remains a
later upgrade path.

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 4: Wire pixelateSwap into growth theme/variant switches

**Files:**
- Modify: `web/src/routes/growth.tsx`

Current facts (verified): `select(id)` is called from gallery chips (line 306); `adopt(i)` from variant dishes (line 373 writes localStorage then bumps `adoptedTick`); the canvas element is rendered by this route (find the `<canvas` JSX; the mount handle is `handle.current`).

- [ ] **Step 1: Wire** — import `pixelateSwap` and wrap the two state changes. Read the route first to locate `select` and `adopt` definitions (near lines 240-260), then:

- `select`: if the current implementation is `const select = (id: string) => { ...setSelected(id)... }`, wrap its body:

```tsx
const select = (id: string) => {
  const canvas = canvasRef.current
  if (canvas) pixelateSwap(canvas, () => selectInner(id))
  else selectInner(id)
}
```

where `selectInner` is the original body extracted verbatim. Same pattern for `adopt(i)`.
- `canvasRef`: the route already holds a ref to the canvas it mounts the workbench on (find it; it exists because `mountWorkbench(canvas, ...)` needs it). Use that exact ref name.

Timing note: the workbench swaps organism state synchronously in `setOrganism` (seed + settled replay happen inside the call), but React state → effect → `handle.current.setOrganism` runs on the NEXT render tick, after `pixelateSwap` snapshots. That is exactly right: the snapshot is the OLD organism, the live canvas re-renders the NEW one underneath the dissolving overlay within a frame or two.

Positioning prerequisite: the overlay is absolutely positioned inside `canvas.parentElement` — verify the canvas parent has `position: relative` (or `fixed`/`absolute`) in `growth.css`; if not, add `position: relative;` to that wrapper's rule in `web/src/routes/growth.css`.

- [ ] **Step 2: Visual check** — dev server `/growth`: Playwright-click a different gallery chip; capture at +150ms (old dish dissolving into blocks over the new culture) and +800ms (clean). Click a variant dish, same pair. Reduced-motion: no overlay ever (`document.querySelector('.pixelate-overlay')` null right after click).

- [ ] **Step 3: Gate + commit**

```bash
git add web/src/routes/growth.tsx web/src/routes/growth.css
git commit -m "feat(web): growth theme and variant switches wipe through pixelateSwap

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 5: Phase + sprint verification

- [ ] The Task 1 gate artifact (before/after diff output showing maxdiff 0) is pasted into the task report.
- [ ] Growth compositor pair posted for user taste sign-off; grain/vignette tuned if asked.
- [ ] Full-app smoke (all six phases now live): `/` reflow + viewer morph + dissolve; `/inbox` ring + scramble; `/transit` heading; `/profile` meter + scroll rack; `/map` coast/glide; `/grove` compositor; `/growth` compositor + wipes. One reduced-motion sweep across all of it: every mid-transition equals its settled state.
- [ ] `vp test && vp check && vp build` clean; bundle delta accounted for (gsap + postprocessing only); tree clean; push.
- [ ] Close out: update `docs/uiux-polish-sprint.md` checkboxes for everything shipped, note deviations (mask reveal consolidation, ScrollReveal narrowed to profile, 2D pixelate instead of GLSL, SplitHeading transit-only) in a short "as-built" section at the bottom of that file, and commit.

## Self-review checklist

1. The refactor commit and the effect commit are SEPARATE (the gate lives between them).
2. `SeededGrainEffect` reused from Phase 4 — not redefined.
3. No edits inside `growth/shaders.ts`, `growth/dna.ts`, `growth/topology.ts`, `growth/layout.ts`.
4. `pixelateSwap` never throws when the 2d context or drawImage fails (WebGL canvas readback with lost context) — every failure path still calls `swap()`.
