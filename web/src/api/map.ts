import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'

export type MapDomain = { label: string; n: number; x: number; y: number }
export type MapGroup = { label: string; n: number; x?: number; y?: number; weight?: number; domain?: number }
export type MapLayout = { groups: MapGroup[]; params: Record<string, number> }
export type MapAllLayout = MapLayout & { domains: MapDomain[] }
export type MapData = { v?: number; points: MapPoint[]; all: MapAllLayout; content: MapLayout }

export type MapPoint = { x: number; y: number; z3: [number, number, number]; t: string; c: string; u?: string; d?: string; g: number; r: number; img?: boolean; cx?: number; cy?: number; c3?: [number, number, number]; th?: number; dom: number }

export const isMapV2 = (data: MapData): boolean => data.v === 2 && Array.isArray(data.all.domains)

export const fetchMap = () => apiGet<MapData>('/api/map')

export const useMap = () => useQuery({ queryKey: ['map'], queryFn: fetchMap })
