import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'

export type MapData = {
  points: MapPoint[]
  all: MapLayout
  content: MapLayout
}

export type MapPoint = { x: number; y: number; z3: [number, number, number]; t: string; c: string; u?: string; d?: string; g: number; r: number; img?: boolean; cx?: number; cy?: number; c3?: [number, number, number]; th?: number }
export type MapLayout = { groups: Array<{ label: string; n: number; x?: number; y?: number; weight?: number }>; params: Record<string, number> }

export const fetchMap = () => apiGet<MapData>('/api/map')

export const useMap = () => useQuery({ queryKey: ['map'], queryFn: fetchMap })
