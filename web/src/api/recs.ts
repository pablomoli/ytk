import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type RecKind = "movie" | "show" | "anime" | "book" | "manga";
export type RecStatus = "want" | "seen" | "skip" | null;

export type RecCard = {
  key: string;
  kind: RecKind;
  title: string;
  year: number | null;
  creator: string | null;
  poster: string | null;
  rating: number | null;
  overview: string | null;
  external_url: string | null;
  count: number;
  sources: { title: string; path: string }[];
  status: RecStatus;
};

export function useRecs() {
  return useQuery({
    queryKey: ["recs"],
    queryFn: () => apiGet<{ recs: RecCard[] }>("/api/recs").then((r) => r.recs),
  });
}

export function useSetRecStatus() {
  return useMutation({
    mutationFn: ({ key, status }: { key: string; status: RecStatus }) =>
      apiSend<{ ok: true }>(`/api/recs/${encodeURIComponent(key)}/status`, "POST", { status }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["recs"] }),
  });
}
