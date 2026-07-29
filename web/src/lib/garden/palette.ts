// Decorative, authored topic identities. These values are aesthetic presets;
// distances between their colors do not encode semantic distance.
export type Vec3 = readonly [number, number, number];

export type CosinePalette = {
  a: Vec3;
  b: Vec3;
  c: Vec3;
  d: Vec3;
};

export const PALETTE_IDS = [
  "verdigris",
  "ember",
  "ultraviolet",
  "cobalt",
  "orchid",
  "citrine",
  "sea-glass",
  "oxide",
  "silver-screen",
  "chlorophyll",
] as const;

export type PaletteId = (typeof PALETTE_IDS)[number];

// Coefficients stay deliberately restrained: paletteStrength can open them
// up, while the defaults remain botanical rather than full-spectrum neon.
export const PALETTES: Record<PaletteId, CosinePalette> = {
  verdigris: {
    a: [0.34, 0.46, 0.4],
    b: [0.2, 0.25, 0.18],
    c: [0.8, 0.65, 0.72],
    d: [0.08, 0.24, 0.38],
  },
  ember: {
    a: [0.48, 0.28, 0.16],
    b: [0.34, 0.2, 0.12],
    c: [0.72, 0.8, 0.62],
    d: [0.02, 0.12, 0.27],
  },
  ultraviolet: {
    a: [0.35, 0.25, 0.48],
    b: [0.22, 0.18, 0.28],
    c: [0.68, 0.82, 0.64],
    d: [0.18, 0.06, 0.34],
  },
  cobalt: {
    a: [0.2, 0.34, 0.53],
    b: [0.12, 0.22, 0.3],
    c: [0.72, 0.68, 0.52],
    d: [0.3, 0.12, 0.02],
  },
  orchid: {
    a: [0.48, 0.27, 0.42],
    b: [0.28, 0.18, 0.2],
    c: [0.62, 0.76, 0.58],
    d: [0.1, 0.28, 0.42],
  },
  citrine: {
    a: [0.5, 0.43, 0.2],
    b: [0.26, 0.24, 0.14],
    c: [0.7, 0.6, 0.82],
    d: [0.2, 0.06, 0.34],
  },
  "sea-glass": {
    a: [0.24, 0.46, 0.47],
    b: [0.16, 0.22, 0.2],
    c: [0.62, 0.75, 0.68],
    d: [0.02, 0.2, 0.38],
  },
  oxide: {
    a: [0.46, 0.31, 0.24],
    b: [0.25, 0.18, 0.2],
    c: [0.74, 0.62, 0.54],
    d: [0.08, 0.28, 0.48],
  },
  "silver-screen": {
    a: [0.43, 0.45, 0.5],
    b: [0.14, 0.16, 0.2],
    c: [0.58, 0.7, 0.64],
    d: [0.16, 0.3, 0.46],
  },
  chlorophyll: {
    a: [0.3, 0.46, 0.19],
    b: [0.18, 0.25, 0.12],
    c: [0.72, 0.58, 0.8],
    d: [0.28, 0.08, 0.4],
  },
};

/** Stable FNV-1a hash; topic color never depends on payload ordering. */
export function stableHash(value: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

export function paletteIdFor(topic: string, requested?: string): PaletteId {
  if (requested && Object.prototype.hasOwnProperty.call(PALETTES, requested))
    return requested as PaletteId;
  return PALETTE_IDS[stableHash(topic) % PALETTE_IDS.length];
}

export function paletteFor(topic: string, requested?: string): CosinePalette {
  return PALETTES[paletteIdFor(topic, requested)];
}

export function palettePhase(topic: string): number {
  return stableHash(`${topic}:phase`) / 0xffffffff;
}

export function paletteOffset(topic: string): number {
  return (stableHash(`${topic}:offset`) % 10_000) / 10_000;
}

export function sampleCosinePalette(palette: CosinePalette, t: number): Vec3 {
  const channel = (i: 0 | 1 | 2) =>
    Math.min(
      1,
      Math.max(
        0,
        palette.a[i] + palette.b[i] * Math.cos(Math.PI * 2 * (palette.c[i] * t + palette.d[i])),
      ),
    );
  return [channel(0), channel(1), channel(2)];
}
