# Real Masonry Tiling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CSS-grid rowspan+`dense` masonry hack with a shortest-column JS masonry that preserves newest-first order and renders landscape (>= 1.3 aspect) cards two columns wide.

**Architecture:** A pure, DOM-free `computeMasonryLayout` function in `web/src/lib/masonry.ts` does all placement math (unit-tested). `MasonryGrid.tsx` is thin DOM glue: it marks cards wide when their image loads landscape, measures card heights at target width, calls the pure function, and writes absolute `left/top/width` positions. CSS drops all grid properties; `.masonry` becomes a relative container with JS-set height.

**Tech Stack:** React 19, TypeScript, vitest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-14-inbox-masonry-tiling-design.md`

## Global Constraints

- Gap is 12px, minimum column width 190px (same visual rhythm as today).
- Wide threshold: `naturalWidth / naturalHeight >= 1.3`.
- Layout must be deterministic: ties break leftmost; no `Date.now()`/`Math.random()`.
- Cards are laid out strictly in DOM order (sort in `queueItems.ts` is correct — do not touch it).
- Wide cards fall back to 1 column when only 1 column fits.
- No emojis anywhere. Do not add conversational comments; match existing comment style.
- All commands run from `web/`: `pnpm test`, `pnpm build`.
- Commit messages end with:
  `Claude-Session: https://claude.ai/code/session_01MLPj4uNxjE78rdgDEfVsXa`

---

### Task 1: Pure layout function `computeMasonryLayout`

**Files:**
- Rewrite: `web/src/lib/masonry.ts` (currently exports only `spanFor`; `spanFor` is deleted — its sole consumer is rewritten in Task 2)
- Rewrite: `web/src/lib/masonry.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces (Task 2 relies on these exact signatures):
  ```ts
  export type MasonryBox = { height: number; wide: boolean }
  export type MasonryPlacement = { left: number; top: number; width: number }
  export type MasonryLayout = {
    nCols: number
    colW: number
    placed: MasonryPlacement[]
    height: number
  }
  export function columnSpec(
    width: number,
    gap?: number,   // default 12
    colMin?: number // default 190
  ): { nCols: number; colW: number }
  export function computeMasonryLayout(
    boxes: MasonryBox[],
    opts: { width: number; gap?: number; colMin?: number },
  ): MasonryLayout
  ```

**Note:** Task 2 rewrites the only consumer of `spanFor` (`MasonryGrid.tsx`). Between Task 1 and Task 2 the build is broken (`MasonryGrid.tsx` imports a deleted export) — that is expected; `pnpm test` still passes because vitest only compiles the test's import graph. Do not run `pnpm build` until Task 2.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `web/src/lib/masonry.test.ts` with:

```ts
import { expect, test } from 'vitest'
import { columnSpec, computeMasonryLayout } from './masonry'

// width 802 with gap 12, colMin 190: floor((802+12)/(190+12)) = floor(4.02) = 4
test('columnSpec derives column count and width', () => {
  const { nCols, colW } = columnSpec(802)
  expect(nCols).toBe(4)
  expect(colW).toBeCloseTo((802 - 3 * 12) / 4)
})

test('columnSpec never returns fewer than one column', () => {
  expect(columnSpec(50).nCols).toBe(1)
  expect(columnSpec(50).colW).toBe(50)
})

test('empty input yields empty layout with zero height', () => {
  const layout = computeMasonryLayout([], { width: 802 })
  expect(layout.placed).toEqual([])
  expect(layout.height).toBe(0)
})

test('boxes fill columns left to right in DOM order', () => {
  // 4 equal boxes on 4 columns: one per column, all at top: 0
  const boxes = Array.from({ length: 4 }, () => ({ height: 100, wide: false }))
  const { placed, colW } = computeMasonryLayout(boxes, { width: 802 })
  expect(placed.map((p) => p.top)).toEqual([0, 0, 0, 0])
  expect(placed.map((p) => p.left)).toEqual([0, 1, 2, 3].map((c) => c * (colW + 12)))
})

test('next box lands in the shortest column', () => {
  // col heights after first 4: [112, 312, 312, 312] -> 5th goes to col 0
  const boxes = [
    { height: 100, wide: false },
    { height: 300, wide: false },
    { height: 300, wide: false },
    { height: 300, wide: false },
    { height: 50, wide: false },
  ]
  const { placed } = computeMasonryLayout(boxes, { width: 802 })
  expect(placed[4].left).toBe(0)
  expect(placed[4].top).toBe(100 + 12)
})

test('ties break leftmost', () => {
  const boxes = [
    { height: 100, wide: false },
    { height: 100, wide: false },
    { height: 100, wide: false },
    { height: 100, wide: false },
    { height: 100, wide: false },
  ]
  const { placed } = computeMasonryLayout(boxes, { width: 802 })
  expect(placed[4].left).toBe(0)
})

test('wide box spans two columns and advances both', () => {
  const boxes = [
    { height: 200, wide: true },
    { height: 100, wide: false },
    { height: 100, wide: false },
  ]
  const { placed, colW } = computeMasonryLayout(boxes, { width: 802 })
  // wide box: cols 0+1, width 2*colW + gap
  expect(placed[0]).toEqual({ left: 0, top: 0, width: 2 * colW + 12 })
  // next two 1-col boxes go to the empty cols 2 and 3, not under the wide box
  expect(placed[1].top).toBe(0)
  expect(placed[2].top).toBe(0)
  // a fourth box must now land under whichever is shortest; cols 0/1 are at
  // 212, cols 2/3 at 112 -> next lands in col 2
  const more = computeMasonryLayout(
    [...boxes, { height: 100, wide: false }],
    { width: 802 },
  )
  expect(more.placed[3].left).toBeCloseTo(2 * (colW + 12))
  expect(more.placed[3].top).toBe(100 + 12)
})

test('wide box picks the adjacent pair with the lowest max height', () => {
  // col heights after setup (each includes its trailing gap):
  // [312, 112, 112, 312]; pair maxes: (0,1)=312, (1,2)=112, (2,3)=312
  // -> wide box goes to pair (1,2) at top 112
  const boxes = [
    { height: 300, wide: false },
    { height: 100, wide: false },
    { height: 100, wide: false },
    { height: 300, wide: false },
    { height: 50, wide: true },
  ]
  const { placed, colW } = computeMasonryLayout(boxes, { width: 802 })
  expect(placed[4].left).toBeCloseTo(1 * (colW + 12))
  expect(placed[4].top).toBe(100 + 12)
})

test('wide box falls back to one column when only one column fits', () => {
  const { placed, colW } = computeMasonryLayout(
    [{ height: 100, wide: true }],
    { width: 200 },
  )
  expect(placed[0].width).toBe(colW)
})

test('container height is the tallest column without trailing gap', () => {
  const boxes = [
    { height: 100, wide: false },
    { height: 250, wide: false },
  ]
  const { height } = computeMasonryLayout(boxes, { width: 802 })
  expect(height).toBe(250)
})
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd web && pnpm test src/lib/masonry.test.ts`
Expected: FAIL — `columnSpec` / `computeMasonryLayout` not exported.

- [ ] **Step 3: Implement**

Replace the entire contents of `web/src/lib/masonry.ts` with:

```ts
export type MasonryBox = { height: number; wide: boolean }
export type MasonryPlacement = { left: number; top: number; width: number }
export type MasonryLayout = {
  nCols: number
  colW: number
  placed: MasonryPlacement[]
  height: number
}

export function columnSpec(width: number, gap = 12, colMin = 190): { nCols: number; colW: number } {
  const nCols = Math.max(1, Math.floor((width + gap) / (colMin + gap)))
  return { nCols, colW: (width - (nCols - 1) * gap) / nCols }
}

/* Shortest-column masonry. Boxes are placed strictly in input order: each
   1-col box drops into the currently shortest column, each wide box into the
   adjacent column pair whose taller side is lowest. Ties break leftmost, so
   the layout is deterministic and never puts a box above an earlier one in
   its column. */
export function computeMasonryLayout(
  boxes: MasonryBox[],
  opts: { width: number; gap?: number; colMin?: number },
): MasonryLayout {
  const gap = opts.gap ?? 12
  const { nCols, colW } = columnSpec(opts.width, gap, opts.colMin ?? 190)
  const cols = new Array<number>(nCols).fill(0)
  const placed: MasonryPlacement[] = []

  for (const box of boxes) {
    if (box.wide && nCols >= 2) {
      let c = 0
      let top = Math.max(cols[0], cols[1])
      for (let i = 1; i < nCols - 1; i++) {
        const h = Math.max(cols[i], cols[i + 1])
        if (h < top) {
          top = h
          c = i
        }
      }
      placed.push({ left: c * (colW + gap), top, width: 2 * colW + gap })
      cols[c] = cols[c + 1] = top + box.height + gap
    } else {
      let c = 0
      for (let i = 1; i < nCols; i++) if (cols[i] < cols[c]) c = i
      const top = cols[c]
      placed.push({ left: c * (colW + gap), top, width: colW })
      cols[c] = top + box.height + gap
    }
  }

  const height = placed.length ? Math.max(...cols) - gap : 0
  return { nCols, colW, placed, height }
}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd web && pnpm test src/lib/masonry.test.ts`
Expected: PASS (10 tests). Do NOT run `pnpm build` yet — `MasonryGrid.tsx` still imports the deleted `spanFor`; Task 2 fixes it.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/masonry.ts web/src/lib/masonry.test.ts
git commit -m "feat(web): shortest-column masonry layout function

Replaces spanFor (CSS-grid rowspan hack) with a pure, order-preserving
shortest-column packer supporting 2-column-wide boxes.

Claude-Session: https://claude.ai/code/session_01MLPj4uNxjE78rdgDEfVsXa"
```

---

### Task 2: DOM glue, CSS, and skeletons

**Files:**
- Rewrite: `web/src/components/MasonryGrid.tsx`
- Modify: `web/src/styles.css:1-13` (`.masonry` block), `web/src/styles.css:21-26` (`.empty` block)
- Modify: `web/src/components/Skeletons.tsx`

**Interfaces:**
- Consumes (from Task 1, exact): `columnSpec(width: number, gap?: number, colMin?: number): { nCols: number; colW: number }` and `computeMasonryLayout(boxes: { height: number; wide: boolean }[], opts: { width: number; gap?: number; colMin?: number }): { nCols: number; colW: number; placed: { left: number; top: number; width: number }[]; height: number }` from `../lib/masonry`.
- Produces: `MasonryGrid` keeps its exact public API (`{ children: ReactNode }`), so `inbox.tsx` and `index.tsx` need no changes. Wide cards are marked with `data-wide="1"` on the `.card` root.

- [ ] **Step 1: Rewrite `MasonryGrid.tsx`**

Replace the entire contents of `web/src/components/MasonryGrid.tsx` with:

```tsx
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
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
  if (img.naturalWidth / img.naturalHeight >= WIDE_RATIO) card.dataset.wide = '1'
}

export function MasonryGrid({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const grid = ref.current
    if (!grid) return

    let raf = 0
    const relayout = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const width = grid.clientWidth
        if (!width) return
        const items = [...grid.children].filter(
          (el): el is HTMLElement => el instanceof HTMLElement,
        )
        /* Two passes because height depends on width: first size every card
           for its span, then measure and place. Cards are absolutely
           positioned with explicit widths, so offsetHeight reflects content
           at that width and relayout stays idempotent (no ratchet). */
        const { nCols, colW } = columnSpec(width, GAP, COL_MIN)
        items.forEach((el) => {
          const wide = el.dataset.wide === '1' && nCols >= 2
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
      })
    }

    relayout()

    const ro = new ResizeObserver(relayout)
    ro.observe(grid)

    const onLoad = (e: Event) => {
      markWide(e.target as HTMLImageElement)
      relayout()
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
  })

  return (
    <main ref={ref} className="masonry">
      {children}
    </main>
  )
}
```

Notes for the implementer:
- The effect deliberately has no dependency array (same as the current code): it re-runs after every render, which re-attaches listeners to images added by the infinite window and re-triggers layout.
- The ResizeObserver fires once more when we set `grid.style.height`; the relayout is deterministic so it converges immediately. Do not "fix" this with observer disconnection.

- [ ] **Step 2: Update CSS**

In `web/src/styles.css`, replace the `.masonry` block (lines 1-13, including the align-items comment — that comment describes the old rowspan ratchet and no longer applies) with:

```css
.masonry {
  /* Positioning context for JS masonry: MasonryGrid measures each child,
     packs shortest-column-first, and writes left/top/width/height in px. */
  position: relative;
}

.masonry > * {
  position: absolute;
  top: 0;
  left: 0;
}
```

In the `.empty` block (originally lines 21-26), delete only the `grid-column: 1 / -1;` line (the parent is no longer a grid). Keep the rest.

- [ ] **Step 3: Convert Skeletons from row spans to pixel heights**

Replace the entire contents of `web/src/components/Skeletons.tsx` with:

```tsx
const HEIGHTS = [220, 300, 180, 260, 340, 200]

export function Skeletons({ count = 12 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skel" style={{ height: HEIGHTS[i % HEIGHTS.length] }} />
      ))}
    </>
  )
}
```

(The old `gridRowEnd: span N` spans at 8px rows + 12px gaps equal `N*8 + (N-1)*12` px; the new values keep the same varied-height look directly in pixels.)

- [ ] **Step 4: Verify unit tests still pass and the app builds**

Run: `cd web && pnpm test && pnpm build`
Expected: all vitest suites PASS (masonry, queueItems, FreshCard, etc.); `tsc -b && vp build` completes with no type errors. If `FreshCard.test.tsx` or any other component test asserts on grid styles, fix the assertion to match the new layout (no `gridRowEnd` anywhere).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/MasonryGrid.tsx web/src/components/Skeletons.tsx web/src/styles.css
git commit -m "feat(web): order-preserving masonry with 2-col landscape cards

MasonryGrid now absolutely positions cards via computeMasonryLayout:
newest-first DOM order is preserved (the old grid-auto-flow dense
backfilled older cards above newer ones), and cards whose cover loads
at >= 1.3 aspect span two columns.

Claude-Session: https://claude.ai/code/session_01MLPj4uNxjE78rdgDEfVsXa"
```

---

### Task 3: Browser verification

**Files:** none (verification only).

**Interfaces:**
- Consumes: the built app from Task 2.
- Produces: a screenshot confirming order + wide cards, attached to the session.

- [ ] **Step 1: Serve the built app**

The hub at :6969 may be serving a stale build and restarting it drops its in-memory ingest queue — do not touch it. Use vite preview instead:

Run: `cd web && pnpm preview` (in tmux or background; default port 4173).
If `/api/*` requests fail under preview because there is no backend proxy, fall back to `pnpm dev` (vite dev server proxies to the hub) — check `web/vite.config.ts` for the proxy setup first.

- [ ] **Step 2: Screenshot /inbox headless**

Use puppeteer MCP (headless — never open a visible browser) to navigate to `http://localhost:4173/inbox` (or the dev-server port), wait for cards to render, and take a full-page screenshot.

- [ ] **Step 3: Check the three acceptance criteria against the screenshot**

1. Newest item (top of the API's sorted list) renders top-left; scanning any single column top-to-bottom never shows an older item above a newer one.
2. YouTube/landscape cards are visibly two columns wide; portrait covers are one column.
3. No overlapping cards, no giant vertical gaps, container height fits content (no clipped bottom row).

- [ ] **Step 4: Resize check**

Set viewport to 700px wide, re-screenshot: fewer columns, layout reflows, wide cards still span 2 (or collapse to 1 column if only 1 fits).

- [ ] **Step 5: Report**

Send the screenshots to the user with a one-line verdict per criterion. No commit (no file changes).
