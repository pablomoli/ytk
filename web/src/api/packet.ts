import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

/* The packet page and its track (#213). Shapes mirror ytk.headless.packet
   and ytk.headless.track; `t` is an ISO instant for a replay, absent for
   live. Both poll: the page is a HUD of what is in flight. */

export type Station = { name: string; since: string; note: string; model: boolean };

export type TrackPacket = {
  id: number;
  title: string;
  source: string;
  station: Station;
  rounds: number;
  calls: number;
  tokens: number;
};

export type Track = { t: string; stations: string[]; cap: number; packets: TrackPacket[] };

export type Finding = { check: string; where: string; detail: string };
export type SpotCheck = { grounded: boolean; where: string; claim: string };
export type ModelRow = {
  model: string | null;
  tokens: number;
  seconds: number;
  at: string;
  view_hash: string | null;
};
export type DraftSummary = {
  thesis: string;
  concepts: number;
  insights: number;
  moments: number;
  tags: string[];
};
export type Round = {
  n: number;
  opened_at: string;
  closed_at: string | null;
  view_hash: string;
  take_kind: string | null;
  findings: Finding[];
  passed: boolean | null;
  layer: string | null;
  bounces: Finding[];
  spots: SpotCheck[];
  draft: DraftSummary | null;
  writer: ModelRow | null;
  marker: ModelRow | null;
};
export type PacketAsk = {
  id: number;
  kind: string;
  why: string;
  options: string[];
  created_at: string;
  attempt: number | null;
  view_hash: string | null;
  links: { target: string | null; title: string | null; why: string }[];
  answer: { choice: string; text: string | null; at: string } | null;
};
export type TrailRow = {
  at: string;
  who: string;
  what: string;
  right: string;
  error: boolean;
  model: boolean;
  tokens: number;
};
export type TranscriptLine = { s: number; text: string; hit: boolean } | { fold: number };
export type PacketFrame = { id: string; t: number | null; shown: boolean; url: string };
export type PacketView = {
  hash: string;
  bundle: string;
  source: string;
  origin: string;
  duration: number | null;
  nlines: number;
  lines: TranscriptLine[];
  shown: string[];
  openable: string[];
  not_shown: string[];
  gaps: string[];
  budget: { frames_shown?: number; evidence_cap_chars?: number; sheet?: string };
  tokenizer: string;
  nframes: number;
  frames: PacketFrame[];
};
export type Agreement = {
  status: "same" | "mismatch" | "none" | "pending";
  draft: string | null;
  grade: string | null;
};
export type Packet = {
  id: number;
  title: string;
  source: string;
  url: string;
  t: string;
  state: string | null;
  station: Station | null;
  calls: number;
  cap: number;
  tokens: number;
  rounds: number;
  running: boolean;
  take: { kind: string; text: string } | null;
  view: PacketView | null;
  agreement: Agreement;
  attempts: Round[];
  asks: PacketAsk[];
  trail: TrailRow[];
  commands: { view: string; grade: string; item: string };
};

const withT = (path: string, t?: string) => (t ? `${path}?t=${encodeURIComponent(t)}` : path);

export function useTrack(t?: string) {
  return useQuery({
    queryKey: ["packet", "track", t ?? "live"],
    queryFn: () => apiGet<Track>(withT("/api/packet", t)),
    refetchInterval: t ? false : 5_000,
  });
}

export function usePacket(id: number, t?: string) {
  return useQuery({
    queryKey: ["packet", id, t ?? "live"],
    queryFn: () => apiGet<Packet>(withT(`/api/packet/${id}`, t)),
    refetchInterval: t ? false : 5_000,
  });
}
