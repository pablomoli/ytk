import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export type QueueItem = {
  url: string;
  source: string;
  author?: string;
  preview_url?: string;
  shared_at?: string;
  text?: string | null;
  /* Content title, distinct from author (creator provenance). May be null
     even when the item has a title-bearing source (#163). */
  title?: string | null;
  attachments?: { url: string; kind: string }[] | null;
  n?: number;
  /* Reflection prompting (#98): curated question on ~1 in 10 items,
     deterministic per url; answered flips once an answer is stored. */
  reflection_question?: string | null;
  reflection_answered?: boolean;
};

export const fetchQueue = () => apiGet<{ items: QueueItem[] }>("/api/queue").then((r) => r.items);
export const useQueue = () => useQuery({ queryKey: ["queue"], queryFn: fetchQueue });
