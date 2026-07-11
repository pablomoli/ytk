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

// Poll once per second only while a job is running; when idle, stop polling so
// the inbox does not re-render (and MasonryGrid does not relayout) every second.
// Add/refresh mutations invalidate ['job'] to kick a fresh poll when they may
// have started work.
export const useJobStatus = () =>
  useQuery({
    queryKey: ['job'],
    queryFn: fetchJob,
    refetchInterval: (query) => (query.state.data?.running ? 1000 : false),
  })
