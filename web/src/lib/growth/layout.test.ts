import { expect, test } from 'vitest'
import { workbenchRegions } from './layout'

test('stage dominates, four tiles fill the right column', () => {
  const { stage, mutations } = workbenchRegions(1200, 800)
  expect(mutations).toHaveLength(4)
  expect(stage.w).toBeGreaterThan(700)
  expect(stage.h).toBe(800)
  for (const m of mutations) {
    expect(m.x).toBeGreaterThanOrEqual(stage.w)
    expect(m.w).toBeGreaterThan(100)
  }
  const ys = mutations.map((m) => m.y)
  expect(new Set(ys).size).toBe(4)
})

test('regions never overlap or exceed bounds', () => {
  const { stage, mutations } = workbenchRegions(900, 620)
  for (const m of mutations) {
    expect(m.x + m.w).toBeLessThanOrEqual(900)
    expect(m.y + m.h).toBeLessThanOrEqual(620)
    expect(m.x).toBeGreaterThanOrEqual(stage.x + stage.w)
  }
})
