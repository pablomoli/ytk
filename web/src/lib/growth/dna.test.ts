import { expect, test } from 'vitest'
import { DEFAULT_CONSTRAINTS, deriveDNA, mutateDNA, RELIQUARY, type ThemeInput } from './dna'

const theme: ThemeInput = {
  id: 'th-creative',
  label: 'creative coding',
  weight: 0.8,
  n_notes: 40,
  fresh_notes: 10,
  tagCounts: { 'creative-coding': 18, 'cool-vis': 12, touchdesigner: 4 },
}

test('derivation is deterministic and complete', () => {
  const a = deriveDNA(theme, DEFAULT_CONSTRAINTS)
  const b = deriveDNA(theme, DEFAULT_CONSTRAINTS)
  expect(a).toEqual(b)
  expect(a.palette).toHaveLength(5)
  const ops = Object.values(a.operators)
  expect(Math.max(...ops)).toBeLessThanOrEqual(1)
  expect(Math.min(...ops)).toBeGreaterThanOrEqual(0)
})

test('creative-coding themes emphasize LACE and BLEED', () => {
  const dna = deriveDNA(theme, DEFAULT_CONSTRAINTS)
  expect(dna.operators.LACE).toBeGreaterThan(dna.operators.DEEPEN)
  expect(dna.operators.BLEED).toBeGreaterThan(dna.operators.MEMBRANE)
})

test('fitness themes emphasize DEEPEN and BUD', () => {
  const dna = deriveDNA(
    { ...theme, id: 'th-fit', tagCounts: { fitness: 10, mma: 6 } },
    DEFAULT_CONSTRAINTS,
  )
  expect(dna.operators.DEEPEN).toBeGreaterThan(dna.operators.LACE)
  expect(dna.operators.BUD).toBeGreaterThan(dna.operators.STIPPLE)
})

test('constraints clamp asymmetry floor', () => {
  const dna = deriveDNA(theme, { ...DEFAULT_CONSTRAINTS, asymmetry_min: 0.9 })
  expect(dna.params.asymmetry).toBeGreaterThanOrEqual(0.9)
})

test('mutations are deterministic, distinct, and clamped', () => {
  const dna = deriveDNA(theme, DEFAULT_CONSTRAINTS)
  const m1 = mutateDNA(dna, 1, DEFAULT_CONSTRAINTS)
  expect(mutateDNA(dna, 1, DEFAULT_CONSTRAINTS)).toEqual(m1)
  expect(m1).not.toEqual(mutateDNA(dna, 2, DEFAULT_CONSTRAINTS))
  expect(m1.params.asymmetry).toBeGreaterThanOrEqual(DEFAULT_CONSTRAINTS.asymmetry_min)
  expect(m1.themeId).toBe(dna.themeId)
})

test('reliquary preset is a valid seed', () => {
  expect(RELIQUARY.palette).toHaveLength(5)
  expect(RELIQUARY.name).toMatch(/reliquary/i)
})
