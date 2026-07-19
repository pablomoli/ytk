import { expect, test } from 'vitest'
import { DEFAULT_CONSTRAINTS } from './dna'
import { parsePhilosophy } from './philosophy'

test('reads constraint numbers from frontmatter', () => {
  const text = `---\nglow_max: 0.2\nasymmetry_min: 0.6\ncurvature_min: 0.4\nsaturation_max: 0.7\n---\n\nNever reads as a graph.`
  expect(parsePhilosophy(text)).toEqual({
    glow_max: 0.2,
    asymmetry_min: 0.6,
    curvature_min: 0.4,
    saturation_max: 0.7,
  })
})

test('missing keys fall back per-key', () => {
  const text = `---\nglow_max: 0.1\n---\nprose`
  const c = parsePhilosophy(text)
  expect(c.glow_max).toBe(0.1)
  expect(c.asymmetry_min).toBe(DEFAULT_CONSTRAINTS.asymmetry_min)
})

test('no frontmatter returns defaults', () => {
  expect(parsePhilosophy('just prose')).toEqual(DEFAULT_CONSTRAINTS)
})
