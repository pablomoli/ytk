// The globe's terrain: land wherever the tiles of the current arrangement sit, sea where none do.
// Texel contract of the planet shader: 0.5 is the shoreline, higher is further inland.

// a sphere covered evenly by n tiles has no sea: the widest gap of an even packing is the shore distance
export const coastRadius = (n: number) => 0.6 * Math.sqrt((4 * Math.PI) / Math.max(1, n));

/** Equirect field (w x h, row 0 at the south pole, z up) of the blended distance to the nearest tiles. */
export function coastField(dirs: ArrayLike<number>, w: number, h: number, out = new Uint8Array(w * h)): Uint8Array {
  const n = Math.floor(dirs.length / 3);
  const coast = coastRadius(n), beta = 3 / coast;
  // tiles further than this add under e^-12 to the blend
  const near = Math.cos(Math.min(Math.PI, 4 * coast));
  for (let j = 0; j < h; j++) {
    const lat = ((j + 0.5) / h - 0.5) * Math.PI;
    const cl = Math.cos(lat), z = Math.sin(lat);
    for (let i = 0; i < w; i++) {
      const lon = ((i + 0.5) / w - 0.5) * 2 * Math.PI;
      const x = cl * Math.cos(lon), y = cl * Math.sin(lon);
      let sum = 0, best = -1;
      for (let k = 0; k < n; k++) {
        const d = x * dirs[k * 3] + y * dirs[k * 3 + 1] + z * dirs[k * 3 + 2];
        if (d > best) best = d;
        if (d > near) sum += Math.exp(-beta * Math.acos(Math.min(1, d)));
      }
      const dist = sum > 0 ? -Math.log(sum) / beta : Math.acos(Math.max(-1, Math.min(1, best)));
      out[j * w + i] = Math.round(255 * Math.max(0, Math.min(1, 0.5 - (dist - coast) / (5 * coast))));
    }
  }
  return out;
}
