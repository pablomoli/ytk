import { describe, expect, it } from 'vitest'
import { isMapV2 } from './map'
import type { MapData } from './map'

const base = { points: [], content: { groups: [], params: {} } }

describe('isMapV2', () => {
  it('accepts a v2 payload with domains', () => {
    const data = { ...base, v: 2, all: { groups: [], params: {}, domains: [] } } as unknown as MapData
    expect(isMapV2(data)).toBe(true)
  })
  it('rejects a legacy payload', () => {
    const data = { ...base, all: { groups: [], params: {} } } as unknown as MapData
    expect(isMapV2(data)).toBe(false)
  })
})
