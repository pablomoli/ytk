import { describe, expect, it } from 'vitest'
import { focusHash, focusLevel, groupTargets, legendRows, parseFocusHash, pointPhases, ramp } from './mapGroups'
import type { MapDomain, MapGroup, MapPoint } from '../api/map'

const domains: MapDomain[] = [
  { label: 'epicmap', n: 2000, x: 0, y: 0 },
  { label: 'ytk', n: 300, x: 1, y: 1 },
  { label: 'other', n: 100, x: -1, y: -1 },
]
const groups: MapGroup[] = [
  { label: 'County GIS', n: 200, domain: 0, x: 0, y: 0 },
  { label: 'Modal Components', n: 150, domain: 0, x: 0.2, y: 0 },
  { label: 'Vault Search', n: 80, domain: 1, x: 1, y: 1 },
]

describe('ramp', () => {
  it('is a clamped cosine ease from 0 to 1', () => {
    expect(ramp(-1)).toBe(0)
    expect(ramp(0)).toBe(0)
    expect(ramp(0.5)).toBeCloseTo(0.5)
    expect(ramp(1)).toBe(1)
    expect(ramp(2)).toBe(1)
  })
})

describe('focusLevel', () => {
  it('classifies focus depth', () => {
    expect(focusLevel({})).toBe('overview')
    expect(focusLevel({ dom: 0 })).toBe('domain')
    expect(focusLevel({ dom: 0, sub: 1 })).toBe('sub')
  })
})

describe('groupTargets', () => {
  it('overview: everything full', () => {
    const t = groupTargets(3, groups, {}, undefined, new Set())
    expect([...t.dom]).toEqual([1, 1, 1])
    expect([...t.sub]).toEqual([1, 1, 1])
  })
  it('domain focus dims other domains', () => {
    const t = groupTargets(3, groups, { dom: 0 }, undefined, new Set())
    expect(t.dom[0]).toBe(1)
    expect(t.dom[1]).toBeCloseTo(0.08)
    expect(t.sub[2]).toBeCloseTo(0.08) // subtopic of another domain
  })
  it('sub focus dims sibling subtopics but keeps them above other domains', () => {
    const t = groupTargets(3, groups, { dom: 0, sub: 0 }, undefined, new Set())
    expect(t.sub[0]).toBe(1)
    expect(t.sub[1]).toBeCloseTo(0.25) // sibling within focused domain
    expect(t.dom[1]).toBeCloseTo(0.08)
  })
  it('hover overrides focus - never dim both', () => {
    const t = groupTargets(3, groups, { dom: 0 }, { dom: 1 }, new Set())
    expect(t.dom[1]).toBe(1) // hovered wins
    expect(t.dom[0]).toBeCloseTo(0.08) // focused recedes while hover is live
  })
  it('hidden domains are 0 regardless', () => {
    const t = groupTargets(3, groups, {}, { dom: 1 }, new Set([1]))
    expect(t.dom[1]).toBe(0)
  })
})

describe('legendRows', () => {
  it('sorts domains by size and nests subs only for the focused domain', () => {
    const rows = legendRows(domains, groups, { dom: 0 })
    expect(rows.map((r) => r.label)).toEqual(['epicmap', 'ytk', 'other'])
    expect(rows[0].subs.map((s) => s.label)).toEqual(['County GIS', 'Modal Components'])
    expect(rows[1].subs).toEqual([])
  })
})

describe('focus hash round-trip', () => {
  it('serializes with slugified labels and parses back', () => {
    expect(focusHash({ dom: 0, sub: 1 }, domains, groups)).toBe('#d:epicmap:modal-components')
    expect(parseFocusHash('#d:epicmap:modal-components', domains, groups)).toEqual({ dom: 0, sub: 1 })
    expect(parseFocusHash('#d:nope', domains, groups)).toEqual({})
    expect(focusHash({}, domains, groups)).toBe('')
  })
})

describe('pointPhases', () => {
  it('normalizes distance from the subtopic centroid per group', () => {
    const points = [
      { z3: [0, 0, 0], g: 0, dom: 0 },
      { z3: [3, 0, 0], g: 0, dom: 0 },
      { z3: [1, 0, 0], g: 0, dom: 0 },
      { z3: [0.5, 0, 0], g: -1, dom: 2 },
    ] as unknown as MapPoint[]
    // group-0 centroid x = 4/3: distances 4/3, 5/3, 1/3 -> phases 0.8, 1.0, 0.2
    const phases = pointPhases(points)
    expect(phases[1]).toBe(1) // farthest in its group
    expect(phases[0]).toBeCloseTo(0.8)
    expect(phases[2]).toBeCloseTo(0.2)
    expect(phases[3]).toBe(0) // sole noise point of its domain sits on its own centroid
  })
})
