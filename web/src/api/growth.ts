import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type GrowthPhilosophy = { text: string; path: string };

export function useGrowthPhilosophy() {
  return useQuery({
    queryKey: ["growth-philosophy"],
    queryFn: () => apiGet<GrowthPhilosophy>("/api/growth/philosophy"),
  });
}

export function useSaveGrowthPhilosophy() {
  return useMutation({
    mutationFn: (text: string) =>
      apiSend<{ saved: boolean }>("/api/growth/philosophy", "PUT", { text }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["growth-philosophy"] }),
  });
}
