import { CanvasTexture } from "three";
import type { OrbPoint } from "../../api/orb";

export const ATLAS_SIZE = 4096;
export const TILE = 128;
export const COLS = ATLAS_SIZE / TILE; // 32 -> 1024 slots; design breaks at ~1024 notes

export function uvRect(i: number): { u: number; v: number; s: number } {
  const col = i % COLS;
  const row = Math.floor(i / COLS);
  const s = TILE / ATLAS_SIZE;
  // canvas rows grow downward; UV v grows upward — flip to the tile's bottom edge
  return { u: col * s, v: 1 - (row + 1) * s, s };
}

export function themeColor(th: number, n: number): string {
  const hue = ((th < 0 ? n : th) * 360) / Math.max(1, n + 1);
  return `hsl(${hue.toFixed(0)} 35% 22%)`;
}

export type AtlasHandle = { texture: CanvasTexture; dispose(): void; idle: Promise<void> };

export function buildAtlas(
  points: OrbPoint[],
  nThemes: number,
  onUpdate: () => void,
): AtlasHandle {
  const canvas = document.createElement("canvas");
  canvas.width = ATLAS_SIZE;
  canvas.height = ATLAS_SIZE;
  const ctx = canvas.getContext("2d")!;
  points.forEach((p, i) => {
    const col = (i % COLS) * TILE;
    const row = Math.floor(i / COLS) * TILE;
    ctx.fillStyle = themeColor(p.th, nThemes);
    ctx.fillRect(col, row, TILE, TILE);
  });
  const texture = new CanvasTexture(canvas);
  // RawShaderMaterial has no output-encode chunk, so tagging this sRGB would
  // double-darken; leave NoColorSpace and let the canvas bytes pass through.
  let disposed = false;
  const loads = points.map((p, i) => {
    if (!p.thumb) return Promise.resolve();
    return new Promise<void>((resolve) => {
      const img = new Image();
      img.onload = () => {
        if (disposed) return resolve();
        // cover-crop into the square slot
        const side = Math.min(img.naturalWidth, img.naturalHeight);
        const sx = (img.naturalWidth - side) / 2;
        const sy = (img.naturalHeight - side) / 2;
        const col = (i % COLS) * TILE;
        const row = Math.floor(i / COLS) * TILE;
        ctx.drawImage(img, sx, sy, side, side, col, row, TILE, TILE);
        texture.needsUpdate = true;
        onUpdate();
        resolve();
      };
      img.onerror = () => resolve(); // failed load keeps the theme placeholder
      img.src = `/vault-media/${p.thumb}`;
    });
  });
  return {
    texture,
    idle: Promise.all(loads).then(() => undefined),
    dispose() {
      disposed = true;
      texture.dispose();
    },
  };
}
