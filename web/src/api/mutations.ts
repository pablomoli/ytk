import { useMutation } from "@tanstack/react-query";
import { apiSend, queryClient } from "./client";
import type { PullResult } from "../lib/pullStatus";

export const addUrls = (urls: string[]) => apiSend("/api/queue/add", "POST", { urls });

/* No args -> pull every source, non-forced (the plain "refresh" button, which
   respects the per-source cadence throttle). A selective pull from the source
   menu passes `only` and forces, since the user explicitly picked those now. */
export const refreshSources = (opts?: { only?: string[]; force?: boolean }) => {
  const params = new URLSearchParams();
  if (opts?.force) params.set("force", "true");
  if (opts?.only?.length) params.set("only", opts.only.join(","));
  const qs = params.toString();
  return apiSend<PullResult>(`/api/queue/refresh${qs ? `?${qs}` : ""}`, "POST");
};
export type IngestPayload = {
  urls: string[];
  tags?: string[];
  thought?: string;
  /* url -> answer; absent entirely when nothing was answered (#98). */
  reflections?: Record<string, string>;
};

/* JSON.stringify drops undefined members, so an absent reflections map never
   reaches the wire as a key. */
export const ingest = (payload: IngestPayload) => apiSend("/api/ingest", "POST", payload);

export const reflectAnswer = (url: string, answer: string) =>
  apiSend<{ stored: boolean }>("/api/reflect-answer", "POST", { url, answer });

export const useAddUrls = () =>
  useMutation({
    mutationFn: addUrls,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["queue"] });
      void queryClient.invalidateQueries({ queryKey: ["job"] });
    },
  });

export const useRefreshSources = () =>
  useMutation({
    mutationFn: (opts?: { only?: string[]; force?: boolean }) => refreshSources(opts),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["queue"] });
      void queryClient.invalidateQueries({ queryKey: ["job"] });
    },
  });

export const useIngest = () =>
  useMutation({
    mutationFn: (payload: IngestPayload) => ingest(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["queue"] });
      void queryClient.invalidateQueries({ queryKey: ["job"] });
    },
  });
