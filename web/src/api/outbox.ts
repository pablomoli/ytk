import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type AskProposal = {
  kind: string;
  why?: string;
  options?: string[];
  window_days?: number;
};

export type AskDraft = {
  thesis?: string | null;
  summary?: string | null;
  key_concepts?: string[] | null;
  insights?: string[] | null;
  take_response?: string | null;
};

export type AskObjection = { check?: string | null; detail?: string | null };

export type OutboxAsk = {
  id: number;
  ask_id: number;
  item_id: number;
  subkind: string;
  created_at: string;
  title?: string | null;
  url?: string | null;
  source?: string | null;
  thumbnail?: string | null;
  draft?: AskDraft | null;
  objections?: AskObjection[] | null;
  proposal: AskProposal;
};

export type LoopHealth = { ok: boolean; line: string };

export type Outbox = {
  asks: OutboxAsk[];
  speaks: unknown[];
  parked: { count: number; oldest: string | null };
  loop: LoopHealth | null;
};

export function useOutbox() {
  return useQuery({ queryKey: ["outbox"], queryFn: () => apiGet<Outbox>("/api/outbox") });
}

export type AskAnswer = { ask_id: number; choice: string; text?: string };

export function useAnswerAsk() {
  return useMutation({
    mutationFn: (answer: AskAnswer) =>
      apiSend<{ answer_id: number | null; state: string }>("/api/outbox/answer", "POST", answer),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["outbox"] }),
  });
}
