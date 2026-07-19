import { expect, test } from 'vitest'
import { workbenchRegions } from './layout'

test('stage is the full canvas, four variant dishes bottom-right', () => {
  const { stage, mutations } = workbenchRegions(1200, 800)
  expect(stage).toEqual({ x: 0, y: 0, w: 1200, h: 800 })
  expect(mutations).toHaveLength(4)
  const side = Math.round(Math.min(1200, 800) * 0.17)
  for (const m of mutations) {
    expect(m.w).toBe(side)
    expect(m.h).toBe(side)
    expect(m.y + m.h).toBe(800 - 12)
    expect(m.x + m.w).toBeLessThanOrEqual(1200 - 12 + 1)
  }
  const xs = mutations.map((m) => m.x)
  expect(new Set(xs).size).toBe(4)
  expect(xs[3] + side).toBe(1200 - 12)
})

test('variant dishes stay inside bounds and never overlap', () => {
  const { mutations } = workbenchRegions(900, 620)
  for (let i = 0; i < mutations.length; i++) {
    expect(mutations[i].x).toBeGreaterThan(0)
    expect(mutations[i].y).toBeGreaterThan(0)
    if (i > 0) {
      expect(mutations[i].x).toBeGreaterThanOrEqual(mutations[i - 1].x + mutations[i - 1].w)
    }
  }
})
