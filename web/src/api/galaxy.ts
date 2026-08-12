import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export type GalaxyMoon = { size: number; path: string; title: string; thumb: string | null };

export type GalaxyPlanet = {
  theme: number;
  label: string;
  n: number;
  activity: number;
  cohesion: number;
  cls: string;
  hue: string;
  pos: [number, number, number];
  radius_deg: number;
  tex: string;
  median_age_days: number | null;
  rings: { earned: boolean; partners: { theme: number; z: number }[] };
  spin: { earned: boolean; side: string | null; median_age_days: number | null };
  moons: GalaxyMoon[];
};

export type GalaxyData = { epoch: string; k_deg: number; planets: GalaxyPlanet[] };

export const useGalaxy = () => useQuery({ queryKey: ["galaxy"], queryFn: () => apiGet<GalaxyData>("/api/galaxy") });
