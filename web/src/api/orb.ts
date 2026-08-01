import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export type OrbPoint = {
  p: string; // vault-relative note path — NoteViewer's key
  t: string;
  c: string;
  u?: string | null;
  d?: string | null;
  th: number;
  thumb?: string | null; // vault-relative, served at /vault-media/<thumb>
};

export type LayoutName = "radial" | "haversine" | "lattice";

export type OrbScores = Partial<
  Record<LayoutName, { trustworthiness: number; mean_nn_deg: number; overlap: number; overlap_frac: number }>
>;

export type OrbSphere = {
  radial: number[][];
  haversine: number[][] | null;
  lattice: number[][];
  scores: OrbScores;
  chosen: LayoutName;
};

export type OrbData = { points: OrbPoint[]; themes: string[]; sphere: OrbSphere };

export const fetchOrb = () => apiGet<OrbData>("/api/orb");

export const useOrb = () => useQuery({ queryKey: ["orb"], queryFn: fetchOrb });
