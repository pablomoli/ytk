import type { Station, TrackPacket } from "../api/packet";

/* The track's arithmetic, kept out of the renderer so it can be tested
   without a canvas. Stations are indices into the track's station list:
   runner, proctor, student, spell-checker, teacher, librarian, owner. */

export const STATIONS = [
  "runner",
  "proctor",
  "student",
  "spell-checker",
  "teacher",
  "librarian",
  "owner",
] as const;
export const MODEL_STATIONS = new Set([2, 3, 4, 5]);

/* A minute to ten days fills the ring, blended 0.4 toward linear (locked). */
export const LOGMAX = Math.log10(1 + 60 * 14400);
export const CURVE = 0.4;

export const logp = (s: number) =>
  Math.min(1, Math.max(0, Math.log10(1 + Math.max(0, s))) / LOGMAX);

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export function scaleT(sec: number, curve = CURVE): number {
  const ceil = Math.pow(10, LOGMAX) - 1;
  const g = lerp(0.08, 1, curve);
  const pw = Math.pow(Math.min(1, Math.max(0, sec) / ceil), g);
  return curve <= 0 ? logp(sec) : lerp(logp(sec), pw, Math.min(1, curve * 1.6));
}

export function stationIndex(s: Station): number {
  return STATIONS.indexOf(s.name as (typeof STATIONS)[number]);
}

/* Seconds held at the station as of `nowMs`. */
export function heldFor(s: Station, nowMs: number): number {
  return Math.max(0, (nowMs - Date.parse(s.since)) / 1000);
}

const pad2 = (n: number) => String(n).padStart(2, "0");

export function ago(s: number): string {
  s = Math.max(0, Math.floor(s));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} m ${pad2(s % 60)} s`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ${pad2(Math.floor((s % 3600) / 60))} m`;
  return `${Math.floor(s / 86400)} d ${pad2(Math.floor((s % 86400) / 3600))} h`;
}

export function clockText(ms: number): string {
  const d = new Date(ms);
  return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}`;
}

/* Mean ink over packets that spent any; a bar's width is its share of it. */
export function inkMean(packets: TrackPacket[]): number {
  const v = packets.map((p) => p.tokens).filter((x) => x > 0);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 1;
}

export function inkWeight(tokens: number, mean: number): number {
  return Math.max(0.25, Math.min(3, tokens / mean));
}

/* Packets grouped by station, longest held first; the order j and k walk. */
export function byStation(packets: TrackPacket[], nowMs: number): TrackPacket[][] {
  const out: TrackPacket[][] = STATIONS.map(() => []);
  for (const p of packets) {
    const i = stationIndex(p.station);
    if (i >= 0) out[i]!.push(p);
  }
  for (const arr of out) arr.sort((a, b) => heldFor(b.station, nowMs) - heldFor(a.station, nowMs));
  return out;
}

export function walkOrder(packets: TrackPacket[], nowMs: number): number[] {
  return byStation(packets, nowMs).flatMap((arr) => arr.map((p) => p.id));
}

export function short(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1).trimEnd() + "…";
}
