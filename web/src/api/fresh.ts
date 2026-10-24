import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type FreshNote = {
  path: string;
  stem: string;
  title: string;
  url?: string | null;
  source: string;
  channel?: string | null;
  date?: string | null;
  added: string;
  thumbnail?: string | null;
  tags: string[];
  has_take: boolean;
  preview?: string | null;
  audio?: string | null;
  kind?: string | null;
};

export type SimilarItem = {
  item_id: string;
  title?: string | null;
  url?: string | null;
};

export function useNote(path?: string) {
  return useQuery({
    queryKey: ["note", path],
    queryFn: () =>
      apiGet<{ path: string; content: string }>(`/api/note?path=${encodeURIComponent(path!)}`),
    enabled: Boolean(path),
  });
}

export function useSimilarNotes(path?: string) {
  return useQuery({
    queryKey: ["similar", path],
    queryFn: () => apiGet<SimilarItem[]>(`/api/similar?note=${encodeURIComponent(path!)}&n=8`),
    enabled: Boolean(path),
  });
}

export type NearbyNote = {
  target: string;
  title: string;
  cosine: number;
  path: string | null;
};

export type NearbyNotes = { linkable: boolean; nearby: NearbyNote[] };

export type NearbyLink = {
  target: string;
  target_title: string;
  cosine: number;
  argument: string;
  reindex: string | null;
};

export function useNearbyNotes(path?: string) {
  return useQuery({
    queryKey: ["nearby", path],
    queryFn: () => apiGet<NearbyNotes>(`/api/nearby?note=${encodeURIComponent(path!)}`),
    enabled: Boolean(path),
  });
}

/* A written link leaves the nearby list and lands in the note body, so both refetch. */
export function useLinkNearby(path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (target: string) =>
      apiSend<NearbyLink>("/api/nearby/link", "POST", { note: path, target }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["nearby", path] });
      void client.invalidateQueries({ queryKey: ["note", path] });
    },
  });
}

export function useDeleteNote() {
  return useMutation({
    mutationFn: (path: string) =>
      apiSend<{ deleted: boolean }>("/api/note/delete", "POST", { path }),
    onSuccess: (_, path) => {
      queryClient.setQueryData<FreshNote[]>(["fresh"], (notes) =>
        notes?.filter((note) => note.path !== path),
      );
    },
  });
}
