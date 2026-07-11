import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'

export type MapData = {
  points: Array<Record<string, unknown>>
  all: { groups: Array<{ label: string; n: number }>; params: Record<string, number> }
  content: { groups: Array<{ label: string; n: number }>; params: Record<string, number> }
}

export const fetchMap = () => apiGet<MapData>('/api/map')

export const useMap = () => useQuery({ queryKey: ['map'], queryFn: fetchMap })
