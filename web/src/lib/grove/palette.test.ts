import { describe, expect, test } from 'vite-plus/test'
import { PALETTE_IDS, paletteFor, paletteIdFor, sampleCosinePalette, stableHash } from './palette'

describe('grove palette identity', () => {
  test('is stable for a topic and independent of array position', () => {
    const names = ['visual-craft', 'ai-building', 'epicmap']
    const before = new Map(names.map((name) => [name, paletteIdFor(name)]))
    names.reverse()
    expect(names.map((name) => paletteIdFor(name))).toEqual(names.map((name) => before.get(name)))
  })

  test('honors known authored ids and hashes unknown ids safely', () => {
    expect(paletteIdFor('topic', 'ultraviolet')).toBe('ultraviolet')
    expect(PALETTE_IDS).toContain(paletteIdFor('topic', 'not-a-palette'))
  })

  test('hash and CPU sampler are deterministic', () => {
    expect(stableHash('seed:7')).toBe(stableHash('seed:7'))
    expect(sampleCosinePalette(paletteFor('seed:7'), 0.75)).toEqual(sampleCosinePalette(paletteFor('seed:7'), 0.75))
  })
})
