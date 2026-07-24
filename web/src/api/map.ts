import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'

export type MapDomain = { label: string; n: number; x: number; y: number }
export type MapGroup = { label: string; n: number; x?: number; y?: number; weight?: number; domain?: number }
// Density terrain of a 2D layout (scripts/build_map.py --attach-terrain):
// KDE contour polylines by level index, SCMS ridge polylines with per-vertex
// normalized height [x, y, h], level fractions of the density peak, and a
// downsampled normalized height grid (row-major, ny rows of nx) for relief.
export type MapTerrainGrid = { x0: number; x1: number; y0: number; y1: number; nx: number; ny: number; z: number[] }
export type MapTerrain = { h: number; levels: number[]; fracs?: number[]; contours: Array<{ lv: number; path: number[][] }>; ridges: number[][][]; grid?: MapTerrainGrid }
// Filament web: SCMS ridge curves through the 3D embedding volume; each
// vertex is [x, y, z, label] where label is a domain (all view) or theme
// (content view) index, -1 for unlabeled.
export type MapWeb = { h: number; filaments: number[][][] }
// Monte-Carlo fog: splat samples of the 3D density field, [x, y, z, density]
// with density normalized to the peak over the data (issue #100).
export type MapFog = { h: number; splats: number[][] }
export type MapLayout = { groups: MapGroup[]; params: Record<string, number>; terrain?: MapTerrain; web?: MapWeb; fog?: MapFog }
export type MapAllLayout = MapLayout & { domains: MapDomain[] }
export type MapData = { v?: number; points: MapPoint[]; all: MapAllLayout; content: MapLayout }

export type MapPoint = { x: number; y: number; z3: [number, number, number]; t: string; c: string; u?: string; d?: string; g: number; r: number; img?: boolean; cx?: number; cy?: number; c3?: [number, number, number]; th?: number; dom: number }

export const isMapV2 = (data: MapData): boolean => data.v === 2 && Array.isArray(data.all.domains)

export const fetchMap = () => apiGet<MapData>('/api/map')

export const useMap = () => useQuery({ queryKey: ['map'], queryFn: fetchMap })
