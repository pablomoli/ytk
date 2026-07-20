import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, queryClient } from "./client";

export type ChannelStatus = "loved" | "muted" | null;

export type Channel = {
  key: string;
  source: string;
  channel: string;
  count: number;
  last_seen: string;
  top_tags: string[];
  notes: { title: string; path: string }[];
  status: ChannelStatus;
};

export function useChannels() {
  return useQuery({
    queryKey: ["channels"],
    queryFn: () => apiGet<{ channels: Channel[] }>("/api/channels").then((r) => r.channels),
  });
}

export function useSetChannelStatus() {
  return useMutation({
    mutationFn: ({ key, status }: { key: string; status: ChannelStatus }) =>
      apiSend<{ affinity: Record<string, unknown> }>(
        `/api/channels/${encodeURIComponent(key)}/status`,
        "POST",
        { status },
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["channels"] }),
  });
}
