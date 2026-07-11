import { useMutation, useQuery } from '@tanstack/react-query'
import { apiGet, apiSend, queryClient } from './client'

export type ColorRule = { query: string; color: string }

export type SettingsConfig = {
  filters: { min_duration: number; max_duration: number | null; require_captions: boolean; interest_tags: string[] }
  hub: {
    host: string; port: number; favicon: string; cadence_minutes: Record<string, number>; imessage_gap_minutes: number
    tags: string[]; pinterest_feeds: string[]; enrich_tone: string
  }
  whisper_model: string
  memo_notify: string[]
  github_repos: string[]
  interest: { cluster_min: number; cluster_max: number; content_sources: string[]; alpha: number; explicit_min: number }
  map: { color_rules: ColorRule[]; presets: Record<string, ColorRule[]> }
}

export type SettingsResponse = {
  config: SettingsConfig
  meta: { restart_required_fields: string[]; last_pulls: Record<string, number>; last_pull_at?: number }
}

export type SettingsValidationError = { loc: string; msg: string }

export const fetchSettings = () => apiGet<SettingsResponse>('/api/settings')
export const saveSettings = (config: SettingsConfig) => apiSend<{ saved: boolean; restart_required: boolean }>('/api/settings', 'PUT', config)

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
}

export function useSaveSettings() {
  return useMutation({
    mutationFn: saveSettings,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })
}
