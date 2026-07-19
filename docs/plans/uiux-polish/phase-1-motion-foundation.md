# Phase 1 — Motion Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install GSAP behind a single house-motion module, animate masonry reflow with Flip, and give the NoteViewer a card-to-panel morph entrance with a Bayer-ordered dither reveal on its content.

**Architecture:** `web/src/lib/motion.ts` is the ONLY file allowed to import `gsap` — it registers plugins, creates the house ease, sets defaults, and exports a reduced-motion guard. Masonry reflow uses Flip state capture around the existing layout pass, gated to children changes only. The viewer morph is a transform FLIP (from the clicked card's rect to the dialog panel) plus a `PixelDissolve` overlay whose reveal order comes from a shared seeded Bayer module (`lib/bayer.ts`, reused by Phase 3).

**Tech Stack:** gsap ^3.13 (core + CustomEase, Flip, SplitText, ScrambleTextPlugin, ScrollTrigger — SplitText/ScrambleText registered now, used in Phase 2), React 19.

**Prerequisite:** Phase 0 complete (NoteViewer exists at `web/src/components/NoteViewer.tsx` with props `{ note, onClose }`).

## Global Constraints

See `docs/plans/uiux-polish/README.md`. Phase-specific hard rules:
- After this phase, `grep -rn "from 'gsap'" web/src --include="*.ts" --include="*.tsx" | grep -v lib/motion` must return nothing.
- Every GSAP animation goes through `reducedMotion()` — when true, skip straight to the end state.
- Durations only from `DUR` (0.18 / 0.3 / 0.4 / 0.6). Ease only `'house'`.

---

### Task 1: Install gsap and create `lib/motion.ts`

**Files:**
- Modify: `web/package.json` (via `vp add`)
- Create: `web/src/lib/motion.ts`
- Create: `web/src/lib/motion.test.ts`

**Interfaces (Produces — Phases 2/3 import exactly these names):**

```ts
export { gsap, Flip, SplitText, ScrollTrigger }
export const HOUSE_EASE: string        // 'house' (registered CustomEase)
export const DUR: { base: number; morph: number; wipe: number; reveal: number } // .18/.3/.4/.6
export function reducedMotion(): boolean
```

- [ ] **Step 1: Install** — `cd /Users/melocoton/Developer/ytk/web && vp add gsap`. Verify `package.json` gained `"gsap"` in dependencies.

- [ ] **Step 2: Failing test** — `web/src/lib/motion.test.ts`:

```ts
import { expect, test } from 'vitest'
import { DUR, HOUSE_EASE, gsap, reducedMotion } from './motion'

test('house defaults are wired', () => {
  expect(HOUSE_EASE).toBe('house')
  expect(DUR).toEqual({ base: 0.18, morph: 0.3, wipe: 0.4, reveal: 0.6 })
  expect(gsap.defaults().duration).toBe(0.18)
  expect(typeof reducedMotion()).toBe('boolean')
})
```

jsdom lacks `matchMedia`; vitest setup may not stub it. If the test errors on matchMedia, add to `web/src/test-setup.ts`:

```ts
window.matchMedia ??= ((query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false })) as unknown as typeof window.matchMedia
```

- [ ] **Step 3: Verify failure** — `vp test src/lib/motion.test.ts` → FAIL (module not found).

- [ ] **Step 4: Implement `web/src/lib/motion.ts`**

```ts
import { gsap } from 'gsap'
import { CustomEase } from 'gsap/CustomEase'
import { Flip } from 'gsap/Flip'
import { ScrambleTextPlugin } from 'gsap/ScrambleTextPlugin'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'

/* The single gsap import point for the app. Everything animates on the
   house ease (theme.css --ease) in one of four sanctioned registers.
   Rule: no other file imports 'gsap' — import from here. */
gsap.registerPlugin(CustomEase, Flip, ScrambleTextPlugin, ScrollTrigger, SplitText)

CustomEase.create('house', '0.25,0.1,0.25,1')
export const HOUSE_EASE = 'house'

export const DUR = { base: 0.18, morph: 0.3, wipe: 0.4, reveal: 0.6 } as const

gsap.defaults({ ease: HOUSE_EASE, duration: DUR.base })

/* theme.css kills CSS animation under prefers-reduced-motion, but GSAP
   writes inline styles the kill-switch cannot reach — every JS animation
   must check this and jump to its end state instead. */
export const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

export { Flip, ScrollTrigger, SplitText, gsap }
```

(If `vp check` flags gsap subpath types, the imports above are the documented gsap 3.13 ESM paths; do not switch to `gsap/all` — it defeats tree-shaking.)

- [ ] **Step 5: Verify** — `vp test src/lib/motion.test.ts` → PASS; `vp check` → clean.

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/pnpm-lock.yaml web/src/lib/motion.ts web/src/lib/motion.test.ts web/src/test-setup.ts
git commit -m "feat(web): gsap behind lib/motion.ts — house ease, duration registers, reduced-motion guard

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 2: Seeded Bayer module `lib/bayer.ts`

Pure math shared by the viewer dissolve (this phase) and thumbnail reveals (Phase 3). The 8x8 Bayer matrix mirrors the GLSL `bayer8` already living in `web/src/lib/growth/shaders.ts:137` — same aesthetic, JS-side.

**Files:**
- Create: `web/src/lib/bayer.ts`
- Create: `web/src/lib/bayer.test.ts`

**Interfaces (Produces):**

```ts
export const BAYER8: number[][]                       // 8x8, values 0..63, standard ordered-dither matrix
export function hashString(s: string): number          // deterministic 32-bit-ish hash, always >= 0
export function ditherOrder(cols: number, rows: number, seed: number): number[]
// returns every cell index 0..cols*rows-1 exactly once, ordered by Bayer
// threshold (tiled 8x8) with a small seeded jitter so equal thresholds
// break differently per seed. Deterministic for equal inputs.
```

- [ ] **Step 1: Failing test** — `web/src/lib/bayer.test.ts`:

```ts
import { expect, test } from 'vitest'
import { BAYER8, ditherOrder, hashString } from './bayer'

test('BAYER8 is a permutation of 0..63', () => {
  const flat = BAYER8.flat()
  expect(flat).toHaveLength(64)
  expect([...flat].sort((a, b) => a - b)).toEqual(Array.from({ length: 64 }, (_, i) => i))
})

test('hashString is deterministic and non-negative', () => {
  expect(hashString('sources/youtube/x.md')).toBe(hashString('sources/youtube/x.md'))
  expect(hashString('a')).not.toBe(hashString('b'))
  expect(hashString('anything')).toBeGreaterThanOrEqual(0)
})

test('ditherOrder is a deterministic permutation, seed-sensitive', () => {
  const a = ditherOrder(10, 6, 7)
  expect([...a].sort((x, y) => x - y)).toEqual(Array.from({ length: 60 }, (_, i) => i))
  expect(ditherOrder(10, 6, 7)).toEqual(a)
  expect(ditherOrder(10, 6, 8)).not.toEqual(a)
})
```

- [ ] **Step 2: Verify failure**, then implement `web/src/lib/bayer.ts`:

```ts
/* JS twin of the ordered-dither language in lib/growth/shaders.ts (bayer8).
   Used to order dissolve/reveal cells so DOM transitions rhyme with the
   growth renderer's single-pixel dither at macro scale. */

const bayer2 = [
  [0, 2],
  [3, 1],
]

function expand(matrix: number[][]): number[][] {
  const n = matrix.length
  const out = Array.from({ length: n * 2 }, () => new Array<number>(n * 2).fill(0))
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const v = matrix[y][x] * 4
      out[y][x] = v
      out[y][x + n] = v + 2
      out[y + n][x] = v + 3
      out[y + n][x + n] = v + 1
    }
  }
  return out
}

export const BAYER8 = expand(expand(bayer2))

export function hashString(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

const mulberry = (seed: number) => () => {
  seed |= 0
  seed = (seed + 0x6d2b79f5) | 0
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296
}

export function ditherOrder(cols: number, rows: number, seed: number): number[] {
  const rand = mulberry(seed)
  const cells = Array.from({ length: cols * rows }, (_, i) => {
    const x = i % cols
    const y = Math.floor(i / cols)
    return { i, key: BAYER8[y % 8][x % 8] + rand() * 0.9 }
  })
  return cells.sort((a, b) => a.key - b.key).map((c) => c.i)
}
```

- [ ] **Step 3: Verify** — `vp test src/lib/bayer.test.ts` → PASS; `vp check` clean.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/bayer.ts web/src/lib/bayer.test.ts
git commit -m "feat(web): seeded Bayer ordering module shared by dissolve effects

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 3: Flip-animated masonry reflow

Animate INTENTIONAL relayouts (children changed: filter, delete, load-more) — never resize or image-load relayouts, and never the very first layout.

**Files:**
- Modify: `web/src/components/MasonryGrid.tsx`

- [ ] **Step 1: Implement** — replace the effect body in `MasonryGrid.tsx` (post-Phase 0 version, which has `[children]` deps). Full new component body:

```tsx
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Flip, reducedMotion } from '../lib/motion'
import { columnSpec, computeMasonryLayout } from '../lib/masonry'
import '../styles.css'

const GAP = 12
const COL_MIN = 190
const WIDE_RATIO = 1.3

/* A landscape cover means the card should tile two columns wide. Marked on
   the DOM (not React state) so the layout pass can read it synchronously. */
function markWide(img: HTMLImageElement) {
  if (!img.naturalWidth || !img.naturalHeight) return
  const card = img.closest<HTMLElement>('.card')
  if (!card) return
  if (img.naturalWidth / img.naturalHeight >= WIDE_RATIO) {
    card.dataset.wide = '1'
  } else {
    delete card.dataset.wide
  }
}

type Reason = 'children' | 'resize' | 'load'

export function MasonryGrid({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const laidOut = useRef(false)

  useEffect(() => {
    const grid = ref.current
    if (!grid) return

    let raf = 0
    let pendingReason: Reason = 'children'
    const relayout = (reason: Reason) => {
      /* Flip only on children changes: resize tweens fight the drag, and
         image-load relayouts happen mid-scroll where motion is noise. */
      if (reason === 'children') pendingReason = 'children'
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const width = grid.clientWidth
        if (!width) return
        const items = [...grid.children].filter(
          (el): el is HTMLElement => el instanceof HTMLElement,
        )
        const animate = pendingReason === 'children' && laidOut.current && !reducedMotion()
        const state = animate ? Flip.getState(items) : null
        pendingReason = 'resize'
        /* Two passes because height depends on width: first size every card
           for its span, then measure and place. Cards are absolutely
           positioned with explicit widths, so offsetHeight reflects content
           at that width and relayout stays idempotent (no ratchet). */
        const { nCols, colW } = columnSpec(width, GAP, COL_MIN)
        items.forEach((el) => {
          const wide = el.dataset.wide === '1' && nCols >= 2
          el.style.position = 'absolute'
          el.style.width = `${wide ? 2 * colW + GAP : colW}px`
        })
        const boxes = items.map((el) => ({
          height: el.offsetHeight,
          wide: el.dataset.wide === '1',
        }))
        const layout = computeMasonryLayout(boxes, { width, gap: GAP, colMin: COL_MIN })
        items.forEach((el, i) => {
          el.style.left = `${layout.placed[i].left}px`
          el.style.top = `${layout.placed[i].top}px`
          el.style.width = `${layout.placed[i].width}px`
        })
        grid.style.height = `${layout.height}px`
        laidOut.current = true
        if (state) {
          Flip.from(state, { duration: 0.18, ease: 'house', overwrite: true, onEnter: (els) => els.forEach((el) => ((el as HTMLElement).style.opacity = '1')) })
        }
      })
    }

    relayout('children')

    const ro = new ResizeObserver(() => relayout('resize'))
    ro.observe(grid)

    const onLoad = (e: Event) => {
      markWide(e.target as HTMLImageElement)
      relayout('load')
    }
    const images = [...grid.querySelectorAll('img')]
    images.forEach((img) => {
      if (img.complete) markWide(img)
      img.addEventListener('load', onLoad)
    })

    return () => {
      ro.disconnect()
      images.forEach((img) => img.removeEventListener('load', onLoad))
      if (raf) cancelAnimationFrame(raf)
    }
  }, [children])

  return (
    <main ref={ref} className="masonry">
      {children}
    </main>
  )
}
```

Implementation notes for the executor:
- `pendingReason` collapses coalesced rAF calls: if ANY call in the batch was 'children', the batch animates. It resets to 'resize' after capture so trailing RO ticks don't animate.
- `laidOut` prevents the initial mount from tweening cards in from nothing.
- `Flip.getState` MUST run before the width-assignment pass (the state must be the OLD rects).
- Determinism gate: `web/src/lib/masonry.test.ts` must stay untouched and green — Flip animates what `computeMasonryLayout` decided, it never changes the outputs.

- [ ] **Step 2: Gate** — `cd web && vp test && vp check` → PASS. The MasonryGrid unit test still passes because in jsdom `reducedMotion()` is false but `laidOut.current` is false on the single test layout → no Flip call.

- [ ] **Step 3: Visual check** — with `vp dev --port 5173` running, screenshot `/` at rest, click a source filter chip via Playwright, capture mid-transition (wait 80ms after click) and settled (wait 500ms). Mid-transition should show cards between positions. Repeat with reduced motion: mid-transition capture must equal settled.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/MasonryGrid.tsx
git commit -m "feat(web): Flip-animated masonry reflow on intentional layout changes

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 4: PixelDissolve overlay component

A cover overlay that dissolves away in seeded Bayer order — used by the NoteViewer (this phase) and thumbnail reveals (Phase 3).

**Files:**
- Create: `web/src/components/PixelDissolve.tsx`
- Create: `web/src/components/PixelDissolve.test.tsx`
- Modify: `web/src/styles.css` (append)

**Interfaces (Produces):**

```tsx
PixelDissolve({ seedKey, cell = 28, color = 'var(--bg1)', onDone }: {
  seedKey: string        // deterministic pattern source (e.g. note path)
  cell?: number          // approximate cell size in px
  color?: string         // cell color (should match the surface underneath)
  onDone?: () => void    // fires when the dissolve finishes (or immediately under reduced motion)
})
```

Mount it absolutely over content that is already rendered; it reveals the content by removing itself cell-by-cell. Parent must be `position: relative` (or the dialog panel).

- [ ] **Step 1: Failing test** — `web/src/components/PixelDissolve.test.tsx`:

```tsx
import { render, act } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { PixelDissolve } from './PixelDissolve'

test('renders a deterministic cell grid and completes', () => {
  vi.useFakeTimers()
  const onDone = vi.fn()
  vi.stubGlobal('ResizeObserver', class { observe() {}; disconnect() {}; unobserve() {} })
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 280 })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 140 })
  const { container } = render(<PixelDissolve seedKey="sources/x.md" onDone={onDone} />)
  const cells = container.querySelectorAll('.pixel-dissolve i')
  expect(cells.length).toBe(50) // 280/28 -> 10 cols, 140/28 -> 5 rows
  act(() => { vi.runAllTimers() })
  expect(onDone).toHaveBeenCalledTimes(1)
  Reflect.deleteProperty(HTMLElement.prototype, 'clientWidth')
  Reflect.deleteProperty(HTMLElement.prototype, 'clientHeight')
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
```

- [ ] **Step 2: Verify failure**, then implement `PixelDissolve.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { DUR, reducedMotion } from '../lib/motion'
import { ditherOrder, hashString } from '../lib/bayer'

/* A cover that dissolves in seeded Bayer order: the growth renderer's
   dither language extended to DOM surfaces. CSS transitions carry the
   per-cell fade; JS only assigns the per-cell delay from the order. */
export function PixelDissolve({ seedKey, cell = 28, color = 'var(--bg1)', onDone }: {
  seedKey: string
  cell?: number
  color?: string
  onDone?: () => void
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [grid, setGrid] = useState<{ cols: number; rows: number } | null>(null)
  const [gone, setGone] = useState(false)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    if (reducedMotion()) { setGone(true); onDone?.(); return }
    const cols = Math.max(1, Math.round((host.clientWidth || cell) / cell))
    const rows = Math.max(1, Math.round((host.clientHeight || cell) / cell))
    setGrid({ cols, rows })
    const id = setTimeout(() => { setGone(true); onDone?.() }, DUR.reveal * 1000 + 80)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey])

  const delays = useMemo(() => {
    if (!grid) return []
    const order = ditherOrder(grid.cols, grid.rows, hashString(seedKey))
    const delayByCell = new Array<number>(order.length)
    order.forEach((cellIndex, rank) => { delayByCell[cellIndex] = (rank / order.length) * (DUR.reveal - 0.12) })
    return delayByCell
  }, [grid, seedKey])

  if (gone || !grid) return gone ? null : <div ref={hostRef} className="pixel-dissolve" style={{ background: color }} aria-hidden="true" />

  return (
    <div ref={hostRef} className="pixel-dissolve on" aria-hidden="true"
      style={{ gridTemplateColumns: `repeat(${grid.cols}, 1fr)`, gridTemplateRows: `repeat(${grid.rows}, 1fr)` }}>
      {delays.map((delay, i) => (
        <i key={i} style={{ background: color, transitionDelay: `${delay}s` }} />
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Styles** — append to `web/src/styles.css`:

```css
/* pixel dissolve — cells fade on a per-cell delay set from the Bayer order */
.pixel-dissolve {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: grid;
  pointer-events: none;
}

.pixel-dissolve i {
  opacity: 1;
}

.pixel-dissolve.on i {
  opacity: 0;
  transition: opacity 0.12s var(--ease);
}
```

Mechanism note: cells render opaque, then the `.on` class (present from first paint of the grid state) transitions each to 0 after its `transitionDelay`. Under reduced motion the component renders nothing and fires onDone immediately. theme.css's reduced-motion rule also zeroes the transitions as a second belt.

- [ ] **Step 4: Verify** — `vp test src/components/PixelDissolve.test.tsx` → PASS; `vp check` clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/PixelDissolve.tsx web/src/components/PixelDissolve.test.tsx web/src/styles.css
git commit -m "feat(web): PixelDissolve — seeded Bayer-ordered reveal overlay

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 5: NoteViewer morph entrance + dither reveal

The panel FLIPs from the clicked card's rect to its final rect (300ms), while the panel content resolves under a PixelDissolve seeded by the note path (600ms), both from one interaction.

**Files:**
- Modify: `web/src/components/NoteViewer.tsx`
- Modify: `web/src/components/FreshCard.tsx` (report the clicked card's rect)
- Modify: `web/src/routes/index.tsx`, `web/src/routes/library.tsx` (thread the rect)

**Interfaces:**
- `FreshCard` prop change: `onOpen: (note: FreshNote, rect?: DOMRect) => void` (rect of the card element).
- `NoteViewer` prop change: add optional `originRect?: DOMRect`.
- Routes hold `const [selected, setSelected] = useState<{ note: FreshNote; rect?: DOMRect }>()` instead of a bare note.

- [ ] **Step 1: FreshCard reports its rect** — in `web/src/components/FreshCard.tsx` change the signature and `open`:

```tsx
export function FreshCard({ note, onOpen, onDelete }: {
  note: FreshNote
  onOpen: (note: FreshNote, rect?: DOMRect) => void
  onDelete: (note: FreshNote) => void
}) {
  const cardRef = useRef<HTMLElement>(null)
  ...
  const open = () => onOpen(note, cardRef.current?.getBoundingClientRect())
```

Add `useRef` to the react import and `ref={cardRef}` on the `<article>`. The two `onClick={open}` buttons need no change.

- [ ] **Step 2: Routes thread the rect** — in both `index.tsx` and `library.tsx`:

```tsx
const [selected, setSelected] = useState<{ note: FreshNote; rect?: DOMRect }>();
...
<FreshCard key={item.path} note={item} onOpen={(note, rect) => setSelected({ note, rect })} onDelete={handleDelete} />
...
{selected ? <NoteViewer note={selected.note} originRect={selected.rect} onClose={() => setSelected(undefined)} /> : null}
```

Update the delete-success handlers that referenced `current?.path` to `current?.note.path`.

- [ ] **Step 3: NoteViewer morph** — in `NoteViewer.tsx`, add imports and the entrance effect, and mount the dissolve:

```tsx
import { useEffect, useRef, useState } from 'react'
import { DUR, gsap, reducedMotion } from '../lib/motion'
import { PixelDissolve } from './PixelDissolve'
```

Add state `const [revealing, setRevealing] = useState(true)` and extend the mount effect:

```tsx
useEffect(() => {
  const dialog = dialogRef.current
  if (!dialog) return
  dialog.showModal?.()
  if (originRect && !reducedMotion()) {
    const to = dialog.getBoundingClientRect()
    /* transform FLIP: play the panel from the card's rect into place */
    gsap.from(dialog, {
      duration: DUR.morph,
      x: originRect.left + originRect.width / 2 - (to.left + to.width / 2),
      y: originRect.top + originRect.height / 2 - (to.top + to.height / 2),
      scaleX: originRect.width / to.width,
      scaleY: originRect.height / to.height,
      onComplete: () => gsap.set(dialog, { clearProps: 'transform' }),
    })
  }
  return () => dialog.close?.()
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [])
```

In the JSX, wrap the panel content: keep `.note-panel` as is, and as its FIRST child add:

```tsx
{revealing ? <PixelDissolve seedKey={note.path} onDone={() => setRevealing(false)} /> : null}
```

`.note-panel` is `position: relative` already (Phase 0 CSS), so the overlay covers it.

Signature: `export function NoteViewer({ note, onClose, originRect }: { note: FreshNote; onClose: () => void; originRect?: DOMRect })`.

- [ ] **Step 4: Update NoteViewer tests** — the Phase 0 tests still pass unchanged (no originRect passed → no gsap path). Add one:

```tsx
test('reveal overlay mounts and clears', () => {
  vi.stubGlobal('ResizeObserver', class { observe() {}; disconnect() {}; unobserve() {} })
  const { container } = wrap(<NoteViewer note={note} onClose={() => {}} />)
  expect(container.querySelector('.pixel-dissolve')).toBeInTheDocument()
  vi.unstubAllGlobals()
})
```

(Under jsdom the dissolve grid renders because reducedMotion() is false with the matchMedia stub from Task 1.)

- [ ] **Step 5: Gate** — `cd web && vp test && vp check` → PASS.

- [ ] **Step 6: Visual check** — dev server: on `/`, Playwright-click the first card's `open note` button; capture at +100ms (panel mid-morph, dissolve partially open) and +900ms (settled). Reduced-motion run: +100ms capture equals settled. Close and confirm focus returns to the card (manual note: native dialog restores focus).

- [ ] **Step 7: Commit**

```bash
git add web/src/components/NoteViewer.tsx web/src/components/NoteViewer.test.tsx web/src/components/FreshCard.tsx web/src/routes/index.tsx web/src/routes/library.tsx
git commit -m "feat(web): note viewer morphs from its card and resolves through a Bayer dissolve

Claude-Session: https://claude.ai/code/session_01EZs3WKS79bUuoRYWoS2FsY"
```

---

### Task 6: Phase verification

- [ ] `grep -rn "from 'gsap'" web/src --include='*.ts*' | grep -v lib/motion.ts` → empty.
- [ ] `vp build` succeeds; note the bundle delta in the task report (expected: gsap core + 5 plugins ≈ 60KB gz — the only sanctioned growth).
- [ ] Screenshot matrix (normal + reduced motion): `/` filter-chip reflow mid/settled; viewer open mid/settled. Reduced-motion mids equal their settleds.
- [ ] `vp test && vp check` clean; tree clean; push.

## Self-review checklist

1. Interface drift: `DUR`, `HOUSE_EASE`, `reducedMotion`, `Flip`, `SplitText`, `ScrollTrigger`, `gsap` exported exactly as Phase 2/3 plans expect (they import these names verbatim).
2. `ditherOrder(cols, rows, seed)` signature matches Phase 3's usage.
3. `PixelDissolve` props (`seedKey`, `cell`, `color`, `onDone`) match Phase 3's usage.
4. No `Date.now()`-seeded randomness anywhere — all patterns are seeded by content keys.
