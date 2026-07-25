import { useMutation } from "@tanstack/react-query";
import { apiSend } from "./client";

export type RecapResult = { markdown: string; count: number };

/* On-demand: one Claude call per press, so this is a mutation (an action), not a
   polled query. The fresh feed triggers it and renders the returned narrative. */
export const useRecap = () =>
  useMutation({
    mutationFn: (n?: number) => apiSend<RecapResult>(`/api/recap${n ? `?n=${n}` : ""}`, "POST"),
  });
