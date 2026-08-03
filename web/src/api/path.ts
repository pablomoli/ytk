import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export type PathEndpoint = { title: string; url: string | null; video_id: string | null };
export type PathNote = PathEndpoint & { weight: number };
export type PathStop = { t: number; support: number; notes: PathNote[] };
export type PathData = {
  a: PathEndpoint;
  b: PathEndpoint;
  angle_deg: number;
  background: number;
  stops: PathStop[];
};

const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strOrNull = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

const decodeEndpoint = (raw: unknown): PathEndpoint => {
  const r = (raw ?? {}) as Record<string, unknown>;
  return { title: str(r.title), url: strOrNull(r.url), video_id: strOrNull(r.video_id) };
};

const decodeNote = (raw: unknown): PathNote => {
  const r = (raw ?? {}) as Record<string, unknown>;
  return { ...decodeEndpoint(raw), weight: num(r.weight) };
};

const decodeStop = (raw: unknown): PathStop => {
  const r = (raw ?? {}) as Record<string, unknown>;
  return {
    t: num(r.t),
    support: num(r.support),
    notes: Array.isArray(r.notes) ? r.notes.map(decodeNote) : [],
  };
};

export const decodePath = (raw: unknown): PathData => {
  const r = (raw ?? {}) as Record<string, unknown>;
  return {
    a: decodeEndpoint(r.a),
    b: decodeEndpoint(r.b),
    angle_deg: num(r.angle_deg),
    background: num(r.background),
    stops: Array.isArray(r.stops) ? r.stops.map(decodeStop) : [],
  };
};

export const fetchPath = async (a: string, b: string, stops = 9, k = 3): Promise<PathData> => {
  const qs = new URLSearchParams({ a, b, stops: String(stops), k: String(k) });
  return decodePath(await apiGet<unknown>(`/api/path?${qs.toString()}`));
};

export const usePath = (a?: string, b?: string) =>
  useQuery({
    queryKey: ["path", a, b],
    queryFn: () => fetchPath(a!, b!),
    enabled: Boolean(a && b),
    retry: false,
  });
