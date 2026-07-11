import { useMutation, useQuery } from '@tanstack/react-query'
import { apiGet, apiSend, queryClient } from './client'

export type TagProposal = {
  canonical: string
  variants: string[]
  counts: Record<string, number>
}

export type TagMergeStatus = {
  state: 'idle' | 'running' | 'done' | 'error'
  detail?: string
  proposals: TagProposal[]
}

export type TagMergeResult = { aliases: number; notes: number; videos: number }

export const fetchTagMergeStatus = () => apiGet<TagMergeStatus>('/api/tags/merge/status')

export function useTagMergeStatus() {
  return useQuery({
    queryKey: ['tagMergeStatus'],
    queryFn: fetchTagMergeStatus,
    refetchInterval: (query) => query.state.data?.state === 'running' ? 1_500 : false,
  })
}

export function useProposeTagMerges() {
  return useMutation({
    mutationFn: () => apiSend<{ started: boolean }>('/api/tags/merge/propose', 'POST'),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tagMergeStatus'] }),
  })
}

export function useApplyTagMerges() {
  return useMutation({
    mutationFn: (mapping: Record<string, string>) => apiSend<TagMergeResult>('/api/tags/merge/apply', 'POST', { mapping }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tagMergeStatus'] }),
  })
}
