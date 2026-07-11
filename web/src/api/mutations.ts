import { useMutation } from '@tanstack/react-query'
import { apiSend, queryClient } from './client'

export const addUrls = (urls: string[]) => apiSend('/api/queue/add', 'POST', { urls })
export const refreshSources = () => apiSend('/api/queue/refresh', 'POST')
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
    mutationFn: refreshSources,
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
