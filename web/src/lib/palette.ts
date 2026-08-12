// Mirror of scripts/plot_assets.py's house palette + E31 gallery color rules — change both or change neither.

export const BG = "#08080a";
export const PANEL = "#000000";
export const FRAME = "#2e2e36";
export const TEXT = "#eceae7";
export const MUTED = "#9a968f";
export const GOLD = "#f2b950";
export const CYAN = "#7fd4ff"; // coast contours, per E30 fig_field
export const DIM = "#3a3a42";

export const PUNCH_GAMMA = 0.72;

export const CLASS_HUES: Record<string, string> = {
  V: "#ffb08a",
  IV: "#8a5a3a",
  III: "#5a8cff",
  II: "#cfe0f0",
  I: "#e0cfa0",
};

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.slice(1);
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  return [r, g, b];
}

export function punch(x: number): number {
  const clamped = Math.max(0, Math.min(1, x));
  return clamped ** PUNCH_GAMMA;
}

export function saturation(cohesion: number, lo: number, hi: number): number {
  if (hi === lo) return 1.0;
  const norm = (cohesion - lo) / (hi - lo);
  return 0.3 + 0.7 * norm;
}

export function planetColor(hueHex: string, sat: number): [number, number, number] {
  const hue = hexToRgb(hueHex);
  const dim = hexToRgb(DIM);
  return [
    hue[0] * sat + dim[0] * (1 - sat),
    hue[1] * sat + dim[1] * (1 - sat),
    hue[2] * sat + dim[2] * (1 - sat),
  ];
}
