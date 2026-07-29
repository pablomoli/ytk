import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type ProfileExemplar = {
  title: string;
  source: string;
  thumb?: string | null;
};

export type ProfileTheme = {
  id: string;
  label: string;
  summary: string;
  weight: number;
  n_notes: number;
  fresh_notes?: number;
  exemplars: ProfileExemplar[];
  evidence_ids?: string[];
  note_ids?: string[];
};

export type ProfileClaim = {
  text: string;
  evidence_ids: string[];
};

export type Profile = {
  generated_at: string;
  note_count: number;
  embedding_model?: string | null;
  reanchored_from?: string | null;
  alpha?: number | null;
  profile_markdown: string;
  claims?: ProfileClaim[];
  themes: ProfileTheme[];
};

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: () => apiGet<Profile>("/api/profile"),
    retry: false,
  });
}

export function useRunProfile() {
  return useMutation({
    mutationFn: () => apiSend<{ generated_at: string; themes: number }>("/api/profile/run", "POST"),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["profile"] }),
  });
}

export type GroveBuckets = { text: string; path: string };

export function useGroveBuckets() {
  return useQuery({
    queryKey: ["grove-buckets"],
    queryFn: () => apiGet<GroveBuckets>("/api/grove-buckets"),
  });
}

export function useSaveGroveBuckets() {
  return useMutation({
    mutationFn: (text: string) =>
      apiSend<{ saved: boolean; buckets: string[]; hint: string }>("/api/grove-buckets", "PUT", {
        text,
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["grove-buckets"] }),
  });
}
