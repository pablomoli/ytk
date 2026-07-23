import { useMutation } from '@tanstack/react-query'
import { apiSend, queryClient } from './client'

export const addUrls = (urls: string[]) => apiSend('/api/queue/add', 'POST', { urls })

/* No args -> pull every source, non-forced (the plain "refresh" button, which
   respects the per-source cadence throttle). A selective pull from the source
   menu passes `only` and forces, since the user explicitly picked those now. */
export const refreshSources = (opts?: { only?: string[]; force?: boolean }) => {
  const params = new URLSearchParams()
  if (opts?.force) params.set('force', 'true')
  if (opts?.only?.length) params.set('only', opts.only.join(','))
  const qs = params.toString()
  return apiSend(`/api/queue/refresh${qs ? `?${qs}` : ''}`, 'POST')
}
export const ingest = (urls: string[], tags?: string[], thought?: string) =>
  apiSend('/api/ingest', 'POST', { urls, tags, thought })

export const useAddUrls = () =>
  useMutation({
    mutationFn: addUrls,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['queue'] })
      void queryClient.invalidateQueries({ queryKey: ['job'] })
    },
  })

export const useRefreshSources = () =>
  useMutation({
    mutationFn: (opts?: { only?: string[]; force?: boolean }) => refreshSources(opts),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['queue'] })
      void queryClient.invalidateQueries({ queryKey: ['job'] })
    },
  })

export const useIngest = () =>
  useMutation({
    mutationFn: ({ urls, tags, thought }: { urls: string[]; tags?: string[]; thought?: string }) =>
      ingest(urls, tags, thought),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['queue'] })
      void queryClient.invalidateQueries({ queryKey: ['job'] })
    },
  })
