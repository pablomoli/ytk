import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'

export type QueueItem = {
  url: string
  source: string
  author?: string
  preview_url?: string
  shared_at?: string
  text?: string | null
  n?: number
}

export const fetchQueue = () => apiGet<{ items: QueueItem[] }>('/api/queue').then((r) => r.items)
export const useQueue = () => useQuery({ queryKey: ['queue'], queryFn: fetchQueue })
