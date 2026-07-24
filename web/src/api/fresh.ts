import { useMutation, useQuery } from "@tanstack/react-query";
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

export const fetchFresh = () => apiGet<FreshNote[]>("/api/fresh?n=60");

export function useFreshNotes() {
  return useQuery({ queryKey: ["fresh"], queryFn: fetchFresh });
}

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
