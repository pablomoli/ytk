import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type LsdKind = "third" | "build" | "post" | "whatif";

export type LsdExtra = {
  trail?: string[];
  bridge?: string;
  consequence?: string;
  question?: string;
};

export type LsdCard = {
  id: string;
  kind: LsdKind;
  title: string;
  body: string;
  parents: { id: string; title: string }[];
  extra?: LsdExtra;
};

export type LsdRun = { run_id: string; cards: number; rated: number };

export type LsdDeck = {
  run_id: string;
  cards: LsdCard[];
  ratings: Record<string, number>;
};

export function useLsdRuns() {
  return useQuery({
    queryKey: ["lsd", "runs"],
    queryFn: () => apiGet<{ runs: LsdRun[] }>("/api/lsd/runs").then((r) => r.runs),
  });
}

export function useLsdDeck(run: string | null) {
  return useQuery({
    queryKey: ["lsd", "deck", run],
    queryFn: () => apiGet<LsdDeck>(`/api/lsd/deck?run=${encodeURIComponent(run ?? "")}`),
    enabled: run !== null,
  });
}

export function useRateCard() {
  return useMutation({
    mutationFn: (body: { run_id: string; candidate_id: string; score: number; note: string }) =>
      apiSend<{ ok: true }>("/api/lsd/rate", "POST", body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["lsd"] }),
  });
}
