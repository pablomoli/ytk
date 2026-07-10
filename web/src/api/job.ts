import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'

export type JobStatus = {
  running: boolean
  total: number
  done: number
  current: string | null
  queued: string[]
  failures: string[]
  annotated: number
  linked: string[]
}

export const fetchJob = () => apiGet<JobStatus>('/api/ingest/status')
export const useJobStatus = () => useQuery({ queryKey: ['job'], queryFn: fetchJob, refetchInterval: 1000 })
