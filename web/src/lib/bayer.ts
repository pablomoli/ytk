/* JS twin of the ordered-dither language in lib/growth/shaders.ts (bayer8).
   Used to order dissolve/reveal cells so DOM transitions rhyme with the
   growth renderer's single-pixel dither at macro scale. */

const bayer2 = [
  [0, 2],
  [3, 1],
];

function expand(matrix: number[][]): number[][] {
  const n = matrix.length;
  const out = Array.from({ length: n * 2 }, () => new Array<number>(n * 2).fill(0));
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const v = matrix[y][x] * 4;
      out[y][x] = v;
      out[y][x + n] = v + 2;
      out[y + n][x] = v + 3;
      out[y + n][x + n] = v + 1;
    }
  }
  return out;
}

export const BAYER8 = expand(expand(bayer2));

export function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const mulberry = (seed: number) => () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export function ditherOrder(cols: number, rows: number, seed: number): number[] {
  const rand = mulberry(seed);
  const cells = Array.from({ length: cols * rows }, (_, i) => {
    const x = i % cols;
    const y = Math.floor(i / cols);
    return { i, key: BAYER8[y % 8][x % 8] + rand() * 0.9 };
  });
  return cells.sort((a, b) => a.key - b.key).map((c) => c.i);
}
