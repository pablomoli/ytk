import type { MapData, MapPoint } from '../api/map'

// Adaptive cluster aggregation, ported from the legacy map.html WebGL renderer.
// While a cluster is small on screen its raw points fade out and it condenses
// into one "orb" per spatial sub-cell (preserving silhouette); zooming in
// dissolves the orbs back into points.

export type SubCell = { group: number; indices: number[] }

// The group a point belongs to in a given view: cluster id (`g`) for the
// "everything" layout, theme id (`th`, content-only) for the "content" layout.
export function pointGroup(point: MapPoint, view: 'all' | 'content'): number {
  if (view === 'content') return point.c3 !== undefined ? point.th ?? -1 : -1
  return point.g
}

// Stable 3D layout coordinate used only to bucket points into sub-cells, so the
// partition is independent of the 2D/3D toggle (matches legacy `c = isC ? p.c3 : p.z3`).
function cellCoord(point: MapPoint, view: 'all' | 'content'): [number, number, number] {
  return (view === 'content' ? point.c3 : point.z3) ?? point.z3
}

// Partition each cluster's points into spatial sub-blobs on a fixed grid.
export function subCells(points: MapPoint[], view: 'all' | 'content', cell = 0.13): SubCell[] {
  const cells = new Map<string, SubCell>()
  points.forEach((point, index) => {
    const group = pointGroup(point, view)
    if (group < 0) return
    const c = cellCoord(point, view)
    const key = `${group}:${Math.round(c[0] / cell)}:${Math.round(c[1] / cell)}:${Math.round(c[2] / cell)}`
    let sub = cells.get(key)
    if (!sub) cells.set(key, (sub = { group, indices: [] }))
    sub.indices.push(index)
  })
  return [...cells.values()]
}

export type GroupStat = { n: number; centroid: [number, number, number]; radius: number }

// Per-group centroid and RMS radius in the supplied world positions (already
// resolved for the current view + morph). `groupCount` is the length of the
// active view's group list.
export function groupStats(worlds: number[][], groups: number[], groupCount: number): GroupStat[] {
  const acc = Array.from({ length: groupCount }, () => ({ n: 0, x: 0, y: 0, z: 0, d: 0 }))
  for (let i = 0; i < worlds.length; i++) {
    const g = groups[i]
    if (g < 0 || !acc[g]) continue
    acc[g].n++; acc[g].x += worlds[i][0]; acc[g].y += worlds[i][1]; acc[g].z += worlds[i][2]
  }
  for (const a of acc) if (a.n) { a.x /= a.n; a.y /= a.n; a.z /= a.n }
  for (let i = 0; i < worlds.length; i++) {
    const g = groups[i]
    if (g < 0 || !acc[g]) continue
    const a = acc[g]
    a.d += (worlds[i][0] - a.x) ** 2 + (worlds[i][1] - a.y) ** 2 + (worlds[i][2] - a.z) ** 2
  }
  return acc.map((a) => ({ n: a.n, centroid: [a.x, a.y, a.z] as [number, number, number], radius: a.n ? Math.sqrt(a.d / a.n) : 0 }))
}

// Screen-spread → aggregation factor: 0 = fully condensed into orbs,
// 1 = fully dissolved into points. Matches legacy `clamp((spread - 45) / 70)`.
export function aggFactor(spreadPx: number): number {
  return Math.max(0, Math.min(1, (spreadPx - 45) / 70))
}

export const contentGroupCount = (data: MapData) => data.content.groups.length
export const allGroupCount = (data: MapData) => data.all.groups.length
