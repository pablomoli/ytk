export type Region = { x: number; y: number; w: number; h: number };

// The stage is the whole canvas — a lab bench with the main dish composed in
// shader. The four variant cultures are small square regions bottom-right;
// growth.css positions matching click targets with the same formula
// (side = 0.17 * min(w, h), gap 10, margin 12).
export function workbenchRegions(
  width: number,
  height: number,
): { stage: Region; mutations: Region[] } {
  const side = Math.round(Math.min(width, height) * 0.17);
  const gap = 10;
  const margin = 12;
  const mutations = Array.from({ length: 4 }, (_, i) => ({
    x: width - margin - (4 - i) * side - (3 - i) * gap,
    y: height - margin - side,
    w: side,
    h: side,
  }));
  return { stage: { x: 0, y: 0, w: width, h: height }, mutations };
}
