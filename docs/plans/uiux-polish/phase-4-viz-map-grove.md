# Phase 4 — Viz Track A: Map Feel + Grove Compositor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/map` pans with inertia and zooms on an eased, cursor-anchored glide (zero new dependencies — a MapLibre-style technique port using the file's own exponential-decay idiom). `/grove` gains an EffectComposer pass: vignette + seeded grain + SMAA, nothing drawn that wasn't there.

**Architecture:** All map work stays inside `web/src/lib/mapRenderer.ts`'s existing closure — a velocity buffer feeds a momentum vector integrated in `render()` with the same `1 - Math.exp(-k*dt)` easing the file already uses for morph/dim/flyTo. Grove work swaps the single `renderer.render(scene, camera)` call for a `postprocessing` EffectComposer; the custom grain effect is seeded/static (hash of fragment coords — replays stay reproducible; no time uniform).

**Tech Stack:** `postprocessing` (pmndrs, new dependency — the second and last of the sprint), three.js ^0.185.1.

**Identity rule (non-negotiable):** UMAP layout/projection math and the grove tree topology/DNA are untouched. Everything here is interaction easing or compositor output filtering.

## Global Constraints

See `docs/plans/uiux-polish/README.md`. Phase-specific:
- Momentum decays exponentially — never a spring, never overshoot.
- Momentum cancels on: pointer down, wheel, flyTo (click drill-down), `setView`, `setDimension`, `destroy`.
- Under reduced motion: wheel zoom applies instantly (current behavior), release does not coast.
- Grain intensity is a whisper: 0.05 max. If a screenshot diff shows visible texture at 100% zoom in a flat region, halve it.

---

### Task 1: Map — pure velocity/decay helpers (test-first)

The math lands in `web/src/lib/mapGroups.ts`? No — new file, it is interaction math, not grouping.

**Files:**
- Create: `web/src/lib/mapInertia.ts`
- Create: `web/src/lib/mapInertia.test.ts`

**Interfaces (Produces — consumed by Task 2 inside mapRenderer):**

```ts
export type VelocitySample = { x: number; y: number; t: number }
export function pushSample(buffer: VelocitySample[], sample: VelocitySample, windowMs?: number): void
// appends and drops samples older than windowMs (default 90) relative to sample.t
export function releaseVelocity(buffer: VelocitySample[]): { vx: number; vy: number }
// average velocity in units/ms over the buffered window; {vx:0,vy:0} when < 2 samples
export function decay(value: number, dt: number, k?: number): number
// value * Math.exp(-k * dt), default k = 4 (matches the file's easing register)
```

- [ ] **Step 1: Failing test** — `web/src/lib/mapInertia.test.ts`:

```ts
import { expect, test } from 'vitest'
import { decay, pushSample, releaseVelocity } from './mapInertia'
import type { VelocitySample } from './mapInertia'

test('pushSample drops samples outside the window', () => {
  const buffer: VelocitySample[] = []
  pushSample(buffer, { x: 0, y: 0, t: 0 })
  pushSample(buffer, { x: 1, y: 0, t: 50 })
  pushSample(buffer, { x: 2, y: 0, t: 200 })
  expect(buffer).toHaveLength(2) // t=0 dropped (200-0 > 90)
})

test('releaseVelocity averages displacement over time', () => {
  const buffer: VelocitySample[] = []
  pushSample(buffer, { x: 0, y: 0, t: 0 })
  pushSample(buffer, { x: 10, y: -5, t: 50 })
  const v = releaseVelocity(buffer)
  expect(v.vx).toBeCloseTo(0.2)  // 10px / 50ms
  expect(v.vy).toBeCloseTo(-0.1)
})

test('releaseVelocity is zero with fewer than 2 samples', () => {
  expect(releaseVelocity([])).toEqual({ vx: 0, vy: 0 })
  expect(releaseVelocity([{ x: 1, y: 1, t: 1 }])).toEqual({ vx: 0, vy: 0 })
})

test('decay is exponential and never overshoots', () => {
  expect(decay(1, 0)).toBe(1)
  expect(decay(1, 0.25)).toBeCloseTo(Math.exp(-1))
  expect(decay(-2, 10)).toBeCloseTo(0, 5)
})
```

- [ ] **Step 2: Verify failure**, then implement `web/src/lib/mapInertia.ts`:

```ts
/* Inertial-pan math for the map camera — a technique port of the
   MapLibre release-velocity approach (algorithm only, no dependency).
   Pure and unit-tested; mapRenderer wires it to pointer events. */
export type VelocitySample = { x: number; y: number; t: number }

export function pushSample(buffer: VelocitySample[], sample: VelocitySample, windowMs = 90): void {
  buffer.push(sample)
  while (buffer.length && sample.t - buffer[0].t > windowMs) buffer.shift()
}

export function releaseVelocity(buffer: VelocitySample[]): { vx: number; vy: number } {
  if (buffer.length < 2) return { vx: 0, vy: 0 }
  const first = buffer[0]
  const last = buffer[buffer.length - 1]
  const span = last.t - first.t
  if (span <= 0) return { vx: 0, vy: 0 }
  return { vx: (last.x - first.x) / span, vy: (last.y - first.y) / span }
}

export function decay(value: number, dt: number, k = 4): number {
  return value * Math.exp(-k * dt)
}
```

- [ ] **Step 3: Verify** — `cd web && vp test src/lib/mapInertia.test.ts` → PASS; `vp check` clean.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/mapInertia.ts web/src/lib/mapInertia.test.ts
git commit -m "feat(web): pure inertial-pan math for the map camera

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 2: Map — wire momentum and eased zoom into mapRenderer

`web/src/lib/mapRenderer.ts` current behavior (verified): `up` (line 345) dead-stops the drag; `wheel` (line 348) snaps `scale` instantly with exact cursor anchoring. `render()` (line 300) already eases `morph`, `dimVal`, and the flyTo block with `1 - Math.exp(-k*dt)`.

**Files:**
- Modify: `web/src/lib/mapRenderer.ts`

Anchor edits by content, not line numbers (the file is dense; lines shift).

- [ ] **Step 1: State + import** — add to the imports:

```ts
import { decay, pushSample, releaseVelocity } from './mapInertia'
import type { VelocitySample } from './mapInertia'
```

and alongside the existing camera state declarations (`let drag: ... let moved = 0`):

```ts
let samples: VelocitySample[] = []
let momentum: { vx: number; vy: number } = { vx: 0, vy: 0 }
const killMomentum = () => { momentum = { vx: 0, vy: 0 }; samples = [] }
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches
```

- [ ] **Step 2: Sample during drag** — in `move` (the `if (!drag)` handler), inside the pan branch (the `else` of `if (orbit)`), after `offset = [...]` add:

```ts
pushSample(samples, { x: event.clientX, y: event.clientY, t: performance.now() })
```

and at the top of `move`'s drag branch (before the orbit check), after `flyItem = undefined; scaleTarget = scale;` add `momentum = { vx: 0, vy: 0 }` — a new drag grab kills any coast in progress. Also in `down`, after `drag = { ... }`, add `killMomentum(); samples = [{ x: event.clientX, y: event.clientY, t: performance.now() }]`.

- [ ] **Step 3: Release seeds momentum** — replace `up`:

```ts
const up = () => {
  if (drag && !orbit && !reduceMotion) {
    const v = releaseVelocity(samples) // px/ms in screen space
    // convert to NDC offset units/second: offset spans 2 across the viewport
    momentum = { vx: v.vx * 1000 * 2 / innerWidth, vy: -v.vy * 1000 * 2 / innerHeight }
    if (Math.hypot(momentum.vx, momentum.vy) < 0.02) killMomentum()
  }
  samples = []
  drag = undefined; orbit = false; canvas.classList.remove('dragging')
}
```

(Orbit drags stay momentum-free by design — see sprint doc.)

- [ ] **Step 4: Eased wheel** — replace the body of `wheel` so the TARGET moves and render eases toward it. The existing exact-anchor math moves into the render step, applied incrementally:

```ts
let zoomAnchor: [number, number] | null = null
const wheel = (event: WheelEvent) => {
  event.preventDefault(); flyItem = undefined; killMomentum()
  const rect = canvas.getBoundingClientRect()
  zoomAnchor = [
    (event.clientX - rect.left) / rect.width * 2 - 1,
    1 - (event.clientY - rect.top) / rect.height * 2,
  ]
  scaleTarget = Math.max(.3, Math.min(12, (scaleTarget || scale) * Math.exp(-event.deltaY * .0012)))
  if (reduceMotion) {
    const ratio = scaleTarget / scale
    scale = scaleTarget
    offset = [zoomAnchor[0] - (zoomAnchor[0] - offset[0]) * ratio, zoomAnchor[1] - (zoomAnchor[1] - offset[1]) * ratio]
    zoomAnchor = null
  }
}
```

`scaleTarget` already exists (used by flyTo); it is initialized to 1 like `scale`, so `(scaleTarget || scale)` guards nothing harmful — keep it as written.

- [ ] **Step 5: Integrate in render** — inside `render`, after the `dimVal` easing line and BEFORE the `if (flyItem)` block, add:

```ts
// wheel glide: ease scale to its target, holding the anchor point fixed
if (!flyItem && zoomAnchor && Math.abs(scaleTarget - scale) > 1e-3) {
  const previous = scale
  scale += (scaleTarget - scale) * (1 - Math.exp(-10 * dt))
  const ratio = scale / previous
  offset = [zoomAnchor[0] - (zoomAnchor[0] - offset[0]) * ratio, zoomAnchor[1] - (zoomAnchor[1] - offset[1]) * ratio]
} else if (zoomAnchor && Math.abs(scaleTarget - scale) <= 1e-3) { scale = scaleTarget; zoomAnchor = null }
// pan coast: integrate momentum with exponential decay to a soft stop
if (!drag && (momentum.vx || momentum.vy)) {
  offset = [offset[0] + momentum.vx * dt, offset[1] + momentum.vy * dt]
  momentum = { vx: decay(momentum.vx, dt), vy: decay(momentum.vy, dt) }
  if (Math.hypot(momentum.vx, momentum.vy) < 0.005) killMomentum()
}
```

- [ ] **Step 6: Cancellation sweep** — add `killMomentum()` (and `zoomAnchor = null` where noted) to: `flyTo` (momentum only), `setView` handler (already resets flyItem — add both), `setDimension` (both), `click` when it calls `flyTo` (covered by flyTo), and `destroy` (momentum only, belt-and-braces). The existing `wheel`/`down` cases are handled in Steps 2/4.

- [ ] **Step 7: Gate** — `cd web && vp test && vp check` → PASS (map unit tests `mapGroups.test.ts`, `mapAggregation.test.ts` are untouched — nothing in projection or grouping changed).

- [ ] **Step 8: Visual check** — dev server `/map`: Playwright `page.mouse` drag-and-release, capture at release +200ms and +900ms — the view keeps gliding then rests. Wheel twice, capture mid-glide. Reduced-motion run: release stops dead; wheel is instant.

- [ ] **Step 9: Commit**

```bash
git add web/src/lib/mapRenderer.ts
git commit -m "feat(web): map pan coasts with exponential decay; wheel zoom glides cursor-anchored

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 3: Install postprocessing + seeded grain effect

**Files:**
- Modify: `web/package.json` (via `vp add postprocessing`)
- Create: `web/src/lib/grain.ts` (shared — grove now, growth in Phase 5)

**Interfaces (Produces):** `export class SeededGrainEffect extends Effect` — constructor `(intensity = 0.05)`; static hash-based monochrome grain, no time uniform (deterministic frame-to-frame: replays and screenshots reproduce).

- [ ] **Step 1: Install** — `cd /Users/melocoton/Developer/ytk/web && vp add postprocessing`.

- [ ] **Step 2: Implement `web/src/lib/grain.ts`**:

```ts
import { Effect } from 'postprocessing'

/* Static, seeded film grain: hash of the fragment coordinate, no time
   uniform. Deterministic by design — grove/growth replays must reproduce
   pixel-for-pixel, so the grain must never animate. */
const fragment = /* glsl */ `
uniform float intensity;

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
  float g = hash21(gl_FragCoord.xy) - 0.5;
  outputColor = vec4(inputColor.rgb + g * intensity, inputColor.a);
}
`

export class SeededGrainEffect extends Effect {
  constructor(intensity = 0.05) {
    super('SeededGrainEffect', fragment, {
      uniforms: new Map([['intensity', { value: intensity } as { value: number }]]),
    })
  }
}
```

(The `hash21` is the same hash family as `growth/shaders.ts:127` — one noise dialect across the app. postprocessing's `Effect` uniforms Map accepts three.js `Uniform`-shaped objects; if `vp check` complains about the type, `import { Uniform } from 'three'` and use `new Uniform(intensity)`.)

- [ ] **Step 3: Gate + commit**

```bash
git add web/package.json web/pnpm-lock.yaml web/src/lib/grain.ts
git commit -m "feat(web): postprocessing dependency + seeded static grain effect

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 4: Grove compositor

**Files:**
- Modify: `web/src/lib/grove/scene.ts`

Current state (verified): renderer constructed at line 19 (`antialias: true`); single render call at line 213 (`renderer.render(scene, camera)`); resize at line 206; destroy at line 227.

- [ ] **Step 1: Imports** — add:

```ts
import { EffectComposer, EffectPass, RenderPass, SMAAEffect, ToneMappingEffect, ToneMappingMode, VignetteEffect } from 'postprocessing'
import { SeededGrainEffect } from '../grain'
```

- [ ] **Step 2: Build the composer** — after `const controls = new OrbitControls(...)` block (line 27), add:

```ts
/* Compositor: vignette + filmic tone response + AA + static seeded grain.
   Output filtering only — nothing new is drawn. Grain never animates so
   replays reproduce. */
const composer = new EffectComposer(renderer)
composer.addPass(new RenderPass(scene, camera))
composer.addPass(new EffectPass(
  camera,
  new SMAAEffect(),
  new ToneMappingEffect({ mode: ToneMappingMode.ACES_FILMIC }),
  new VignetteEffect({ offset: 0.3, darkness: 0.55 }),
  new SeededGrainEffect(0.05),
))
```

Also change the WebGLRenderer options at line 19: `antialias: true` → `antialias: false` (SMAA replaces MSAA; MSAA is wasted through a render target).

- [ ] **Step 3: Wire size + render + dispose**:
- `resize` (line 206): after `renderer.setSize(w, h, false)` add `composer.setSize(w, h)`.
- `render` (line 213): replace `renderer.render(scene, camera)` with `composer.render()`.
- `destroy` (line 227): add `composer.dispose()` before `renderer.dispose()`.

- [ ] **Step 4: Gate** — `vp check` clean; `vp test` unchanged (no unit tests cover the scene render call).

- [ ] **Step 5: Visual check** — dev server `/grove`: before/after screenshots at identical camera (fresh load, wait 6s for growth). After shows: subtly darkened corners, slightly compressed highlights on the glow-wire look, smoother edges, whisper of grain. Toggle x-ray look via the UI and re-capture — additive-blend materials must not blow out under ACES (if they do, drop ToneMappingEffect from the pass list and note it in the commit body — vignette+grain+SMAA is the floor).
- Reduced-motion run: identical output (grain is static; nothing here animates) — capture to prove no regression.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/grove/scene.ts
git commit -m "feat(web): grove compositor — SMAA, filmic tone, vignette, seeded grain

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 5: Phase verification

- [ ] Map: coast + glide screenshot pairs (normal), dead-stop pairs (reduced), no console errors during a 30s drag/zoom/click session driven by Playwright.
- [ ] Map determinism: `vp test src/lib/mapGroups.test.ts src/lib/mapAggregation.test.ts src/lib/mapInertia.test.ts` all green.
- [ ] Grove: before/after pair reviewed BY THE USER (vignette/grain are taste calls — post both screenshots and wait for sign-off before considering the task closed).
- [ ] Frame-rate spot check: with the dev server open on `/grove`, run 10s of `page.evaluate(() => new Promise(r => { let n = 0; const t0 = performance.now(); const loop = () => ++n && performance.now() - t0 < 3000 ? requestAnimationFrame(loop) : r(n / 3); requestAnimationFrame(loop); }))` — expect ≥ 45 fps on the M3 (baseline was 41 fps with MSAA; SMAA should not regress it).
- [ ] `vp test && vp check && vp build` clean; tree clean; push.

## Self-review checklist

1. Momentum cancellation list complete: down, move-grab, wheel, flyTo, setView, setDimension, destroy.
2. No spring anywhere — every easing is `exp` decay toward a target.
3. `SeededGrainEffect` has NO time uniform (Phase 5 reuses it under the same determinism contract).
4. UMAP math, tree topology, shader semantics: zero diffs outside the listed integration points.
