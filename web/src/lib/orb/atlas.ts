import { CanvasTexture } from "three";
import type { OrbPoint } from "../../api/orb";

export const ATLAS_SIZE = 4096;
export const TILE = 128; // legacy square slot, kept for callers that still size by it
export const COLS = ATLAS_SIZE / TILE;
// long side of a packed slot. 192 is the largest that fits the current corpus
// (378 landscape, 188 portrait, 64 other, 26 blank) in one 4096 atlas; the
// packer steps down by 15% until a corpus fits, so growth degrades softly.
export const LONG = 192;

export type UvRect = { u: number; v: number; su: number; sv: number };
export type Slot = { x: number; y: number; w: number; h: number };

export function uvRect(i: number): UvRect {
  const col = i % COLS;
  const row = Math.floor(i / COLS);
  const s = TILE / ATLAS_SIZE;
  return { u: col * s, v: 1 - (row + 1) * s, su: s, sv: s };
}

export function slotUv(s: Slot): UvRect {
  // canvas rows grow downward; UV v grows upward — flip to the slot's bottom edge
  return { u: s.x / ATLAS_SIZE, v: 1 - (s.y + s.h) / ATLAS_SIZE, su: s.w / ATLAS_SIZE, sv: s.h / ATLAS_SIZE };
}

// shelf packing: every tile sized by its aspect with the long side = `long`,
// rows sorted tall-first so each shelf wastes little. Returns slots in input order.
export function packSlots(aspects: (number | null | undefined)[], long = LONG): Slot[] {
  const dims = aspects.map((ar) => {
    const a = ar && ar > 0 ? Math.min(2.2, Math.max(1 / 2.2, ar)) : 1;
    return a >= 1 ? { w: long, h: Math.round(long / a) } : { w: Math.round(long * a), h: long };
  });
  const order = dims.map((_, i) => i).sort((a, b) => dims[b].h - dims[a].h || dims[b].w - dims[a].w);
  const slots: Slot[] = new Array(dims.length);
  let x = 0, y = 0, shelf = 0;
  for (const i of order) {
    const { w, h } = dims[i];
    if (x + w > ATLAS_SIZE) { x = 0; y += shelf; shelf = 0; }
    if (shelf === 0) shelf = h;
    if (y + h > ATLAS_SIZE) {
      if (long < 48) throw new Error("orb atlas: corpus does not fit even at 48px");
      return packSlots(aspects, Math.round(long * 0.85));
    }
    slots[i] = { x, y, w, h };
    x += w;
  }
  return slots;
}

export function themeColor(th: number, n: number): string {
  const hue = ((th < 0 ? n : th) * 360) / Math.max(1, n + 1);
  return `hsl(${hue.toFixed(0)} 35% 22%)`;
}

export type AtlasHandle = { texture: CanvasTexture; slots: Slot[]; dispose(): void; idle: Promise<void> };

export function buildAtlas(points: OrbPoint[], nThemes: number, onUpdate: () => void): AtlasHandle {
  const slots = packSlots(points.map((p) => p.ar));
  const canvas = document.createElement("canvas");
  canvas.width = ATLAS_SIZE;
  canvas.height = ATLAS_SIZE;
  const ctx = canvas.getContext("2d")!;
  points.forEach((p, i) => {
    const s = slots[i];
    ctx.fillStyle = themeColor(p.th, nThemes);
    ctx.fillRect(s.x, s.y, s.w, s.h);
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
        // the slot was sized from the server's aspect; cover-fit absorbs any drift
        const s = slots[i];
        const k = Math.max(s.w / img.naturalWidth, s.h / img.naturalHeight);
        const sw = s.w / k, sh = s.h / k;
        ctx.drawImage(img, (img.naturalWidth - sw) / 2, (img.naturalHeight - sh) / 2, sw, sh, s.x, s.y, s.w, s.h);
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
    slots,
    idle: Promise.all(loads).then(() => undefined),
    dispose() {
      disposed = true;
      texture.dispose();
    },
  };
}
