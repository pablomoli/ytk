import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";
import type { FreshNote } from "./fresh";

export type LibraryPage = { total: number; items: FreshNote[] };

export function useLibrary(offset: number, source?: string, q?: string, n = 60) {
  const params = new URLSearchParams({ n: String(n), offset: String(offset) });
  if (source) params.set("source", source);
  if (q) params.set("q", q);
  return useQuery({
    queryKey: ["library", offset, source ?? "", q ?? "", n],
    queryFn: () => apiGet<LibraryPage>(`/api/library?${params}`),
    placeholderData: (prev) => prev,
  });
}
