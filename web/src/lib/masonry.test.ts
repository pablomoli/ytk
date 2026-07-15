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
