import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type ProfileRankPick = {
  url: string;
  title: string;
  source: string;
  theme: string;
  score: number;
};

export type ProfileRankStatus = {
  state: "idle" | "running" | "done" | "error";
  detail: string;
  generated_at: string | null;
  candidates: number;
  picks: ProfileRankPick[];
};

export const fetchProfileRank = () => apiGet<ProfileRankStatus>("/api/queue/profile-rank/status");

export const startProfileRank = () =>
  apiSend<{ started: boolean }>("/api/queue/profile-rank", "POST");

export const useProfileRank = () =>
  useQuery({
    queryKey: ["profile-rank"],
    queryFn: fetchProfileRank,
    refetchInterval: (query) => (query.state.data?.state === "running" ? 1000 : false),
    refetchIntervalInBackground: true,
  });

export const useStartProfileRank = () =>
  useMutation({
    mutationFn: startProfileRank,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["profile-rank"] });
    },
  });
