import { expect, test } from 'vitest'
import { aggFactor, groupStats, pointGroup, subCells } from './mapAggregation'
import type { MapPoint } from '../api/map'

const pt = (over: Partial<MapPoint>): MapPoint => ({ x: 0, y: 0, z3: [0, 0, 0], t: '', c: '', g: 0, r: 0, ...over })

test('pointGroup keys off g for all-view and th for content-view', () => {
  expect(pointGroup(pt({ g: 3 }), 'all')).toBe(3)
  expect(pointGroup(pt({ g: 3, th: 5, c3: [0, 0, 0] }), 'content')).toBe(5)
  // a point without a content embedding has no content group
  expect(pointGroup(pt({ g: 3, th: 5 }), 'content')).toBe(-1)
})

test('subCells partitions each cluster on a fixed grid and skips ungrouped points', () => {
  const points = [
    pt({ g: 0, z3: [0, 0, 0] }),
    pt({ g: 0, z3: [0.01, 0, 0] }), // same cell as the first (within 0.13)
    pt({ g: 0, z3: [1, 0, 0] }), // far cell, same cluster
    pt({ g: 1, z3: [0, 0, 0] }), // different cluster, same coord -> different cell
    pt({ g: -1, z3: [0, 0, 0] }), // ungrouped -> dropped
  ]
  const cells = subCells(points, 'all')
  expect(cells).toHaveLength(3)
  const clusterZero = cells.filter((cell) => cell.group === 0)
  expect(clusterZero).toHaveLength(2)
  expect(clusterZero.flatMap((cell) => cell.indices).sort()).toEqual([0, 1, 2])
  expect(cells.find((cell) => cell.group === 1)?.indices).toEqual([3])
})

test('groupStats computes centroid and RMS radius per group', () => {
  const worlds = [[-1, 0, 0], [1, 0, 0], [0, 0, 0]]
  const groups = [0, 0, 1]
  const stats = groupStats(worlds, groups, 2)
  expect(stats[0].n).toBe(2)
  expect(stats[0].centroid).toEqual([0, 0, 0])
  expect(stats[0].radius).toBeCloseTo(1) // sqrt((1+1)/2)
  expect(stats[1].centroid).toEqual([0, 0, 0])
  expect(stats[1].radius).toBe(0)
})

test('aggFactor ramps 0..1 across the 45..115px spread band', () => {
  expect(aggFactor(45)).toBe(0)
  expect(aggFactor(20)).toBe(0)
  expect(aggFactor(80)).toBeCloseTo(0.5)
  expect(aggFactor(115)).toBe(1)
  expect(aggFactor(300)).toBe(1)
})
