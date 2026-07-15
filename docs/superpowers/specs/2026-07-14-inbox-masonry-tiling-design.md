# Real masonry tiling for the hub grid

Date: 2026-07-14
Status: approved (approach), pending spec review

## Problem

Two complaints about the hub grid (`MasonryGrid`, used by both `/inbox` and the
fresh feed at `/`):

1. **Order looks random.** The queue is sorted newest-first in the DOM
   (`filterAndSortQueue`, `shared_at` descending), but `styles.css` sets
   `grid-auto-flow: row dense`. `dense` backtracks and pulls *later* (older)
   cards up into gaps left by tall cards, so an older item routinely renders
   above/left of a newer one. The sort is correct; the layout re-scrambles it.

2. **16:9 YouTube cards are cramped.** Every card occupies exactly one
   ~190px column. A 16:9 thumbnail rendered at one column width is short and
   small, while portrait covers (TikTok/IG) fill the same column much taller.

The current layout is a CSS-grid *rowspan hack*: `grid-auto-rows: 8px` plus a
JS pass that sets `grid-row-end: span N` from each card's `scrollHeight`. It
only packs tightly *because* of `dense` — and `dense` is exactly what breaks
order. The two are inseparable in that technique.

## The constraint (why this is a real trade, not an effort problem)

Pick two of three:

| | drop `dense` | uniform grid | **real masonry (chosen)** |
|---|:---:|:---:|:---:|
| variable card heights | yes | no (crops) | **yes** |
| no gaps (tight tiling) | no | yes | **yes** |
| strict row-by-row order | yes | yes | column-cascade |

Strict row order + no gaps forces equal heights per row. Keeping variable
heights *and* tight packing means relaxing "row-by-row" to **column-cascade**
order — newest cards fill the top, everything flows downward, and no card ever
sits above a newer one within its column. This is the standard masonry order
(Pinterest, IG Explore). It is what the user asked for.

## Design

Replace the CSS-grid rowspan hack with a JS **shortest-column** masonry that
absolutely-positions cards inside a relative container.

### Pure layout function (`web/src/lib/masonry.ts`)

`spanFor` is removed. New pure, DOM-free, unit-tested function:

```ts
type Box = { height: number; wide: boolean }
type Placed = { left: number; top: number; width: number }
type Layout = { nCols: number; colW: number; placed: Placed[]; height: number }

computeMasonryLayout(boxes: Box[], opts: {
  width: number    // container content width, px
  gap?: number     // default 12 (0.75rem)
  colMin?: number  // default 190
}): Layout
```

Algorithm:

- `nCols = max(1, floor((width + gap) / (colMin + gap)))`
- `colW = (width - (nCols - 1) * gap) / nCols`
- `colHeights = new Array(nCols).fill(0)`
- For each box **in order**:
  - `span = box.wide && nCols >= 2 ? 2 : 1`
  - `span === 1`: choose column `c` with the smallest `colHeights[c]`
    (ties → leftmost). `left = c * (colW + gap)`, `top = colHeights[c]`,
    `width = colW`. Then `colHeights[c] = top + box.height + gap`.
  - `span === 2`: over adjacent pairs `(c, c+1)`, choose the pair with the
    smallest `max(colHeights[c], colHeights[c+1])` (ties → leftmost).
    `top = that max`, `left = c * (colW + gap)`, `width = 2 * colW + gap`.
    Set **both** columns' heights to `top + box.height + gap`.
- `height = max(colHeights) - gap` (drop the trailing gap; `0` if empty).

Determinism: no `Date`/`Math.random`. Tie-break is always leftmost, so output
is stable for identical input.

### DOM glue (`web/src/components/MasonryGrid.tsx`)

Keeps its current effect shape (ResizeObserver + per-image `load` listeners),
but the relayout body changes to:

1. **Mark wide cards.** On each `img` `load`, compute
   `naturalWidth / naturalHeight`. If `>= 1.3`, set `data-wide` on the image's
   closest `.card`; else clear it. (Cards with no image — memo/text/`noimg` —
   stay 1-column.) Landscape detection is source-agnostic: YouTube and any
   other wide thumbnail widen automatically; portrait covers do not.
2. **Two measurement passes** (height depends on width):
   - Pass A: for each `.card`, set `position: absolute` and `width` to `colW`
     or `2*colW+gap` per its `data-wide`. Read back `offsetHeight`.
   - Pass B: call `computeMasonryLayout` with those heights + wide flags, then
     write `left`/`top`/`width` (px) onto each card. Set the container's
     `height` to the returned layout height.
3. Guard against the ratchet bug the old comment warns about: cards are
   `position: absolute` with an explicit `width`, so `offsetHeight` reflects
   content at that width and never feeds back on itself.

### CSS (`web/src/styles.css`)

`.masonry` drops all grid properties, becomes `position: relative` with its
`height` set by JS. Positioning is not owned by the stylesheet: the component
writes `position: absolute` (and left/top/width) inline per child, because a
`.masonry > *` rule ties on specificity with the later `.card { position:
relative }` rule and loses the cascade — exactly the bug inline styles fixed.
`gap` moves from CSS into the layout math (12px).
The `.empty` / skeleton states that relied on `grid-column: 1 / -1` are
adjusted to plain block flow.

## Scope

- Affects both `/inbox` and `/` (fresh feed) — same component, same win.
- Files: `web/src/lib/masonry.ts` (rewrite), `web/src/lib/masonry.test.ts`
  (rewrite for `computeMasonryLayout`), `web/src/components/MasonryGrid.tsx`,
  `web/src/styles.css`.
- No API, backend, or data changes. Sort logic in `queueItems.ts` is already
  correct and is left untouched.

## Testing

- **Unit (vitest):** `computeMasonryLayout` — column count from width; shortest
  column placement; wide box spans two columns and advances both; wide box
  falls back to 1 column when `nCols === 1`; empty input → height 0; leftmost
  tie-break determinism.
- **Manual (browser):** load `/inbox`, confirm newest card is top-left and
  order cascades down with no card above a newer one in its column; YouTube
  cards render two columns wide; resize narrows column count and reflows;
  lazy image loads trigger reflow without the height ratchet.

## Non-goals

- Native CSS `masonry` (not shippable cross-browser in 2026).
- Pixel-perfect row alignment (mutually exclusive with variable heights + no
  gaps, per the constraint table).
- Changing sort order, card contents, or the control rail.
