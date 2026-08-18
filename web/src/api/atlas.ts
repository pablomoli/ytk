import { useQuery } from "@tanstack/react-query";
import { apiGet, apiSend } from "./client";

export type AtlasLatentRef = {
  latent: number;
  name: string | null;
  excess: number;
  outside_null: boolean;
};

export type AtlasCell = {
  cell: [number, number];
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  n_points: number;
  n_scored: number;
  ood_frac: number;
  head_mass: number;
  label_latent: number;
  label: string | null;
  label_excess: number;
  label_outside_null: boolean;
  top5: AtlasLatentRef[];
  seed_cos_top5: number[];
  stable_05: boolean;
  stable_08: boolean;
  theme_label: string | null;
};

export type AtlasData = {
  grid: number;
  x_edges: number[];
  y_edges: number[];
  n_map_points: number;
  n_joined: number;
  gate: { stable_05: number; stable_08: number; strict_05: number; n: number };
  protagonist: {
    latent: number;
    cell: [number, number] | null;
    on_frozen_layout: boolean;
    cell_method: string;
  };
  cells: AtlasCell[];
};

export type FeatureExemplar = {
  title: string;
  kind: string;
  source: string;
  video_id: string | null;
  act: number;
};

export type FeatureCard = {
  name: string | null;
  confidence: string | null;
  freq: number;
  badge: number;
  exemplars: FeatureExemplar[];
};

export type AtlasFeatures = {
  checkpoint: string;
  naming: string;
  protagonist: number;
  cards: Record<string, FeatureCard>;
};

export type KnobResult = {
  base: { title: string; kind: string; source: string; sim: number }[];
  clamped: { title: string; kind: string; source: string; sim: number }[];
  query_latents: { latent: number; act: number }[];
  latent_max: number;
};

export const useAtlas = () =>
  useQuery({ queryKey: ["atlas"], queryFn: () => apiGet<AtlasData>("/api/atlas") });

export const useAtlasFeatures = () =>
  useQuery({
    queryKey: ["atlas-features"],
    queryFn: () => apiGet<AtlasFeatures>("/api/atlas/features"),
  });

export const runKnob = (query: string, latent: number, clamp: number) =>
  apiSend<KnobResult>("/api/atlas/knob", "POST", { query, latent, clamp });
