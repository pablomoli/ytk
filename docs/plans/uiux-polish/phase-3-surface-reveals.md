# Phase 3 — Surface Reveals and Reticle Cursor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thumbnails stop popping in — they resolve through the seeded Bayer dissolve on load; cards get a canvas pixel-bloom hover; an optional brass reticle cursor ships behind a settings toggle on the feed and library routes.

**Architecture:** Thumbnail reveal reuses `PixelDissolve` (Phase 1) triggered by image `onLoad` inside FreshCard — one dissolve treatment across modal and thumbnails (this consolidates the sprint doc's separate "Pixel Image" and "Vertical Tiles" items into the house treatment; record that in the commit). PixelBloom is an owned rewrite of the reactbits PixelCard idea: rAF canvas, center-out bloom from the pointer entry point, palette from theme tokens. TargetCursor is an owned rewrite of reactbits' Target Cursor: brass 1.5px corner brackets, no blend mode, no idle spin, per-route mount, localStorage-gated (`ytk:cursor`), native I-beam preserved over text.

**Tech Stack:** gsap via `lib/motion.ts` (quickTo for the cursor), canvas 2D, React 19. No new packages.

**Prerequisite:** Phase 1 complete (`lib/motion.ts`, `lib/bayer.ts`, `PixelDissolve`).

## Global Constraints

See `docs/plans/uiux-polish/README.md`. Phase-specific:
- The cursor is the sprint's one UX gamble: it must be killable from `/settings` without touching code, must never hide the I-beam over `input`, `textarea`, `[contenteditable]`, or selectable note text, and renders nothing under reduced motion.
- All canvas effects cap devicePixelRatio at 2 and tear down rAF loops on unmount.

---

### Task 1: Thumbnail dissolve on load

**Files:**
- Modify: `web/src/components/FreshCard.tsx`
- Modify: `web/src/components/FreshCard.test.tsx` (read first; keep existing assertions green)

- [ ] **Step 1: Implement** — in `FreshCard.tsx` (post-Phase 1 version), for the thumbnail branch only (`note.thumbnail && !imageFailed`): add loaded state and the overlay. The image branch becomes:

```tsx
) : note.thumbnail && !imageFailed ? (
  <div className="thumb-wrap">
    <img
      src={`/vault-media/${note.thumbnail}`}
      loading="lazy"
      alt=""
      onLoad={() => setRevealed(true)}
      onError={() => setImageFailed(true)}
    />
    {!revealed ? null : reveal ? <PixelDissolve seedKey={note.path} cell={22} color="var(--bg2)" onDone={() => setReveal(false)} /> : null}
  </div>
) : (
```

with state at the top of the component:

```tsx
const [revealed, setRevealed] = useState(false) // image bytes arrived
const [reveal, setReveal] = useState(true)      // dissolve still owed
```

Wait — order matters: the dissolve must START when the image loads, not on mount (lazy images may load seconds later, and MasonryGrid measures on load). The exact logic: overlay renders ONLY after `revealed` flips true, runs once, then unmounts via `onDone`. Before load, the wrap shows the card background (no overlay needed — the img is empty space). The snippet above implements exactly that; read it carefully before typing.

Add `import { PixelDissolve } from './PixelDissolve'` and the `.thumb-wrap` style to `styles.css`:

```css
.thumb-wrap {
  position: relative;
}
```

MasonryGrid interaction note: the dissolve overlay is absolutely positioned and adds no height; `markWide` reads `img.naturalWidth` on the load event, which still fires on the img itself — wrapping in `.thumb-wrap` does not break it because `img.closest('.card')` still resolves. Do NOT change MasonryGrid.

- [ ] **Step 2: Test** — read `FreshCard.test.tsx` first; add:

```tsx
test('thumbnail dissolve mounts after image load', () => {
  vi.stubGlobal('ResizeObserver', class { observe() {}; disconnect() {}; unobserve() {} })
  const { container } = render(<FreshCard note={{ ...note, thumbnail: 't.jpg' }} onOpen={() => {}} onDelete={() => {}} />)
  expect(container.querySelector('.pixel-dissolve')).not.toBeInTheDocument()
  fireEvent.load(container.querySelector('img')!)
  expect(container.querySelector('.pixel-dissolve')).toBeInTheDocument()
  vi.unstubAllGlobals()
})
```

(Adapt the `note` fixture to whatever the existing test file defines; if it defines none, build one like NoteViewer.test.tsx's.)

- [ ] **Step 3: Gate + commit**

Run: `cd web && vp test && vp check` → PASS.

```bash
git add web/src/components/FreshCard.tsx web/src/components/FreshCard.test.tsx web/src/styles.css
git commit -m "feat(web): thumbnails resolve through the seeded Bayer dissolve on load

One dissolve treatment across viewer and thumbnails; supersedes the
sprint doc's separate Pixel Image / Vertical Tiles items.

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 2: PixelBloom hover on cards

**Files:**
- Create: `web/src/components/PixelBloom.tsx`
- Create: `web/src/components/PixelBloom.test.tsx`
- Modify: `web/src/components/Card.tsx` (inbox tiles), `web/src/components/FreshCard.tsx` (feed tiles)
- Modify: `web/src/styles.css` (append)

**Interfaces (Produces):** `PixelBloom()` — self-contained absolutely-positioned canvas that listens to its PARENT's mouseenter/mouseleave (parent must be `position: relative`, which `.card` is). No props.

- [ ] **Step 1: Failing test**:

```tsx
import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { PixelBloom } from './PixelBloom'

test('renders an aria-hidden canvas layer', () => {
  const { container } = render(<div style={{ position: 'relative' }}><PixelBloom /></div>)
  const canvas = container.querySelector('canvas.pixel-bloom')
  expect(canvas).toBeInTheDocument()
  expect(canvas).toHaveAttribute('aria-hidden', 'true')
})
```

- [ ] **Step 2: Verify failure**, then implement `PixelBloom.tsx`:

```tsx
import { useEffect, useRef } from 'react'
import { reducedMotion } from '../lib/motion'
import { BAYER8 } from '../lib/bayer'

const CELL = 14
const BLOOM_MS = 260
const FADE_MS = 220

/* Canvas hover effect: cells bloom center-out from the pointer's entry
   point and recede on leave — the growth dither at interaction scale.
   Pure rAF; the loop only runs while animating. Colors are read from the
   theme at effect start. */
export function PixelBloom() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const host = canvas?.parentElement
    if (!canvas || !host || reducedMotion()) return
    const context = canvas.getContext('2d')
    if (!context) return

    let raf = 0
    let start = 0
    let dir: 1 | -1 = 1
    let origin = { x: 0.5, y: 0.5 }
    let level = 0 // 0 = clear, 1 = fully bloomed

    const draw = (now: number) => {
      const dpr = Math.min(devicePixelRatio || 1, 2)
      const w = host.clientWidth, h = host.clientHeight
      if (canvas.width !== w * dpr) { canvas.width = w * dpr; canvas.height = h * dpr }
      const t = Math.min(1, (now - start) / (dir === 1 ? BLOOM_MS : FADE_MS))
      level = dir === 1 ? t : 1 - t
      context.clearRect(0, 0, canvas.width, canvas.height)
      const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#e2b04a'
      const cols = Math.ceil(w / CELL), rows = Math.ceil(h / CELL)
      const maxDist = Math.hypot(Math.max(origin.x, 1 - origin.x) * w, Math.max(origin.y, 1 - origin.y) * h)
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          const cx = (x + 0.5) * CELL, cy = (y + 0.5) * CELL
          const dist = Math.hypot(cx - origin.x * w, cy - origin.y * h) / maxDist
          const threshold = dist * 0.75 + (BAYER8[y % 8][x % 8] / 64) * 0.25
          if (threshold < level) {
            context.globalAlpha = 0.14 * Math.min(1, (level - threshold) * 6)
            context.fillStyle = accent
            context.fillRect(x * CELL * dpr, y * CELL * dpr, (CELL - 2) * dpr, (CELL - 2) * dpr)
          }
        }
      }
      context.globalAlpha = 1
      if (t < 1) raf = requestAnimationFrame(draw)
      else if (dir === -1) context.clearRect(0, 0, canvas.width, canvas.height)
    }

    const begin = (nextDir: 1 | -1, event?: MouseEvent) => {
      if (event) {
        const rect = host.getBoundingClientRect()
        origin = { x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height }
      }
      dir = nextDir
      start = performance.now()
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(draw)
    }

    const enter = (e: MouseEvent) => begin(1, e)
    const leave = () => begin(-1)
    host.addEventListener('mouseenter', enter)
    host.addEventListener('mouseleave', leave)
    return () => {
      host.removeEventListener('mouseenter', enter)
      host.removeEventListener('mouseleave', leave)
      cancelAnimationFrame(raf)
    }
  }, [])

  return <canvas ref={canvasRef} className="pixel-bloom" aria-hidden="true" />
}
```

- [ ] **Step 3: Styles**:

```css
.pixel-bloom {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
}
```

(z-index 2 sits under `.fresh-card .delete-note`'s z-index 3 — delete stays clickable and visible.)

- [ ] **Step 4: Mount** — add `<PixelBloom />` as the FIRST child of the root element in `Card.tsx` (`<div className={...}>`) and `FreshCard.tsx` (`<article className="card fresh-card">`), with imports. `.card` is `position: relative` (styles.css:266-272) — no CSS change needed.

- [ ] **Step 5: Gate + commit**

```bash
git add web/src/components/PixelBloom.tsx web/src/components/PixelBloom.test.tsx web/src/components/Card.tsx web/src/components/FreshCard.tsx web/src/styles.css
git commit -m "feat(web): PixelBloom canvas hover — center-out Bayer bloom on cards

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 3: TargetCursor behind a settings toggle

**Files:**
- Create: `web/src/components/TargetCursor.tsx`
- Create: `web/src/lib/prefs.ts` (+ `web/src/lib/prefs.test.ts`)
- Modify: `web/src/routes/settings.tsx` (client-side "experiments" section)
- Modify: `web/src/routes/index.tsx`, `web/src/routes/library.tsx` (conditional mount + `data-cursor-target` on cards)
- Modify: `web/src/styles.css` (append)

**Interfaces (Produces):**
- `prefs.ts`: `export const getPref = (key: string): boolean`, `export const setPref = (key: string, on: boolean): void` — localStorage-backed, key namespaced as given; `export const CURSOR_PREF = 'ytk:cursor'`.
- `TargetCursor()` — mounts global listeners; acquires elements marked `data-cursor-target`. Render at route level ONLY when `getPref(CURSOR_PREF)` is true.

- [ ] **Step 1: prefs test-first** — `web/src/lib/prefs.test.ts`:

```ts
import { expect, test } from 'vitest'
import { CURSOR_PREF, getPref, setPref } from './prefs'

test('prefs round-trip through localStorage, default false', () => {
  expect(getPref(CURSOR_PREF)).toBe(false)
  setPref(CURSOR_PREF, true)
  expect(getPref(CURSOR_PREF)).toBe(true)
  setPref(CURSOR_PREF, false)
  expect(getPref(CURSOR_PREF)).toBe(false)
})
```

Implement `web/src/lib/prefs.ts`:

```ts
/* Client-only experiment flags. Deliberately NOT in ~/.ytk/config.yaml:
   these are per-browser toggles, not system configuration. */
export const CURSOR_PREF = 'ytk:cursor'

export const getPref = (key: string): boolean => {
  try { return localStorage.getItem(key) === '1' } catch { return false }
}

export const setPref = (key: string, on: boolean): void => {
  try { on ? localStorage.setItem(key, '1') : localStorage.removeItem(key) } catch { /* private mode */ }
}
```

- [ ] **Step 2: Implement `TargetCursor.tsx`**:

```tsx
import { useEffect, useRef } from 'react'
import { gsap, reducedMotion } from '../lib/motion'

const IDLE = 18 // half-size of the idle reticle box, px
const PAD = 6   // bracket overshoot around an acquired target

/* Brass viewfinder: four corner brackets follow the pointer; hovering a
   [data-cursor-target] element expands the brackets around it. Owned
   rewrite of the reactbits Target Cursor: no blend mode, no idle spin,
   house ease only. Native cursor is preserved over text and inputs. */
export function TargetCursor() {
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root || reducedMotion()) return
    const corners = [...root.children] as HTMLElement[]
    const xTo = gsap.quickTo(root, 'x', { duration: 0.12, ease: 'house' })
    const yTo = gsap.quickTo(root, 'y', { duration: 0.12, ease: 'house' })
    let acquired: HTMLElement | null = null

    const place = (w: number, h: number) => {
      const positions = [
        { x: -w / 2, y: -h / 2 }, { x: w / 2, y: -h / 2 },
        { x: -w / 2, y: h / 2 }, { x: w / 2, y: h / 2 },
      ]
      corners.forEach((corner, i) => gsap.to(corner, { x: positions[i].x, y: positions[i].y, duration: 0.18, ease: 'house' }))
    }

    const move = (event: MouseEvent) => {
      if (acquired) {
        const rect = acquired.getBoundingClientRect()
        xTo(rect.left + rect.width / 2)
        yTo(rect.top + rect.height / 2)
        place(rect.width + PAD * 2, rect.height + PAD * 2)
      } else {
        xTo(event.clientX)
        yTo(event.clientY)
      }
      const overText = (event.target as HTMLElement).closest('input, textarea, [contenteditable], pre, .note-panel')
      root.style.opacity = overText ? '0' : '1'
    }
    const over = (event: MouseEvent) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>('[data-cursor-target]')
      if (target === acquired) return
      acquired = target
      if (!acquired) place(IDLE * 2, IDLE * 2)
    }

    place(IDLE * 2, IDLE * 2)
    addEventListener('mousemove', move)
    addEventListener('mouseover', over)
    return () => { removeEventListener('mousemove', move); removeEventListener('mouseover', over) }
  }, [])

  if (reducedMotion()) return null

  return (
    <div ref={rootRef} className="target-cursor" aria-hidden="true">
      <i /><i /><i /><i />
    </div>
  )
}
```

- [ ] **Step 3: Styles**:

```css
/* brass viewfinder cursor (experiment, settings-gated) */
.target-cursor {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 40;
  pointer-events: none;
  transition: opacity 0.18s var(--ease);
}

.target-cursor i {
  position: absolute;
  width: 9px;
  height: 9px;
  border: 1.5px solid var(--accent);
}

.target-cursor i:nth-child(1) { border-right: 0; border-bottom: 0; translate: -1px -1px; }
.target-cursor i:nth-child(2) { border-left: 0; border-bottom: 0; translate: -8px -1px; }
.target-cursor i:nth-child(3) { border-right: 0; border-top: 0; translate: -1px -8px; }
.target-cursor i:nth-child(4) { border-left: 0; border-top: 0; translate: -8px -8px; }
```

(Deliberately NOT hiding the native cursor anywhere: the reticle floats alongside it. Hiding `cursor: none` globally is the classic ergonomic failure — skip it; the brackets read as an overlay instrument. This is a taste decision the user reviews in verification.)

- [ ] **Step 4: Settings toggle** — in `web/src/routes/settings.tsx`, add before the closing `</main>`:

```tsx
<details open><summary>Experiments</summary><div className="settings-body">
  <label>reticle cursor (feed + library)
    <input type="checkbox" defaultChecked={getPref(CURSOR_PREF)} onChange={(e) => setPref(CURSOR_PREF, e.target.checked)} />
    <span className="settings-pill">takes effect on next route visit</span>
  </label>
</div></details>
```

with `import { CURSOR_PREF, getPref, setPref } from '../lib/prefs'`. This section does NOT touch the draft/save flow (it is client-only, applies independently of the Save bar).

- [ ] **Step 5: Route mounts** — in `index.tsx` and `library.tsx`:

```tsx
{getPref(CURSOR_PREF) ? <TargetCursor /> : null}
```

placed next to the NoteViewer mount, plus imports. Mark acquirable elements: in `FreshCard.tsx` add `data-cursor-target=""` to the `<article>`; in `Card.tsx` to the root div.

- [ ] **Step 6: Gate + commit**

```bash
git add web/src/components/TargetCursor.tsx web/src/lib/prefs.ts web/src/lib/prefs.test.ts web/src/routes/settings.tsx web/src/routes/index.tsx web/src/routes/library.tsx web/src/components/FreshCard.tsx web/src/components/Card.tsx web/src/styles.css
git commit -m "feat(web): brass reticle cursor behind a settings experiment toggle

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 4: Phase verification

- [ ] Screenshots (normal + reduced): `/` fresh load with cold cache (thumbnails mid-dissolve at +400ms, settled at +1500ms); hover a card via Playwright `page.hover` and capture the bloom; enable the cursor pref via `page.evaluate(() => localStorage.setItem('ytk:cursor','1'))`, reload, hover a card, capture brackets acquired.
- [ ] Reduced-motion: no dissolve overlay, no bloom, no cursor at all.
- [ ] Toggle off in `/settings`, revisit `/` — cursor gone.
- [ ] `vp test && vp check && vp build` clean; tree clean; push.

## Self-review checklist

1. `PixelDissolve` consumed with the exact Phase 1 props; no prop invented here.
2. Delete button (z-index 3) still above the bloom canvas (z-index 2).
3. Cursor never sets `cursor: none`; opacity-0 zones cover inputs/textareas/note text.
4. localStorage access is try/catch-guarded (private browsing).
