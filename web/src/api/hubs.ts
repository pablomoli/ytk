import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type HubKind = "creator" | "concept";
export type HubVerdict = "approve" | "strike";

export type HubCandidate = {
  kind: HubKind;
  key: string;
  name: string;
  count: number;
  examples: string[];
  target: string;
  target_path: string;
  hand_made: boolean;
  collision: string;
  verdict: HubVerdict | "pending";
  judged_at: string;
};

type KindSummary = {
  names: number;
  notes: number;
  pending: number;
  approve: number;
  strike: number;
};

export type HubList = {
  threshold: number;
  summary: Record<HubKind, KindSummary>;
  candidates: HubCandidate[];
};

export type HubApplyResult = {
  recorded: number;
  notes_linked: number;
  links: number;
  notes_changed: number;
  hubs_written: number;
  hubs_removed: number;
  foreign_keys: string[];
};

export type HubVerdictChange = { kind: HubKind; key: string; verdict: HubVerdict };

export function useHubList() {
  return useQuery({ queryKey: ["hubList"], queryFn: () => apiGet<HubList>("/api/hubs") });
}

export function useApplyHubVerdicts() {
  return useMutation({
    mutationFn: (verdicts: HubVerdictChange[]) =>
      apiSend<HubApplyResult>("/api/hubs/apply", "POST", { verdicts }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["hubList"] }),
  });
}
