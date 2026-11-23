// The globe's terrain: land wherever the tiles of the current arrangement sit, sea where none do.
// Texel contract of the planet shader: 0.5 is the shoreline, higher is further inland.

// a sphere covered evenly by n tiles has no sea: the widest gap of an even packing is the shore distance
export const coastRadius = (n: number) => 0.6 * Math.sqrt((4 * Math.PI) / Math.max(1, n));

const KIN = 6; // how many nearest tiles a tile is compared with
// the sea level is set so this share of the sphere is land: the coast marks where themes hold together
// better than elsewhere on the same sphere, whatever the arrangement's overall level
export const LAND_SHARE = 0.6;

/** Per tile, the share of its KIN nearest tiles that carry its theme (0 for a tile with none). */
export function cohesion(dirs: ArrayLike<number>, themes: ArrayLike<number>): Float32Array {
  const n = Math.floor(dirs.length / 3), out = new Float32Array(n);
  const top = new Float64Array(KIN), who = new Int32Array(KIN);
  for (let i = 0; i < n; i++) {
    if (!(themes[i] >= 0)) continue;
    top.fill(-2); who.fill(-1);
    for (let j = 0; j < n; j++) {
      if (j === i) continue;
      const d = dirs[i * 3] * dirs[j * 3] + dirs[i * 3 + 1] * dirs[j * 3 + 1] + dirs[i * 3 + 2] * dirs[j * 3 + 2];
      let m = 0;
      for (let k = 1; k < KIN; k++) if (top[k] < top[m]) m = k;
      if (d > top[m]) { top[m] = d; who[m] = j; }
    }
    let same = 0, seen = 0;
    for (let k = 0; k < KIN; k++) if (who[k] >= 0) { seen++; if (themes[who[k]] === themes[i]) same++; }
    out[i] = seen ? same / seen : 1;
  }
  return out;
}

// the value `share` of the sphere's area sits above, and the value 97% sits below (rows weigh by their latitude's width)
function seaLevel(field: Float32Array, w: number, h: number, share: number): { shore: number; high: number } {
  const order = Array.from(field.keys()).sort((a, b) => field[a] - field[b]);
  const rowW = Float32Array.from({ length: h }, (_, j) => Math.cos(((j + 0.5) / h - 0.5) * Math.PI));
  let total = 0, acc = 0, shore = 0, high = 0, found = false;
  for (let j = 0; j < h; j++) total += rowW[j] * w;
  for (const c of order) {
    acc += rowW[Math.floor(c / w)];
    if (!found && acc >= total * (1 - share)) { shore = field[c]; found = true; }
    if (acc >= total * 0.97) { high = field[c]; break; }
  }
  return { shore, high };
}

/** Equirect field (w x h, row 0 at the south pole, z up). Land needs tiles nearby; given themes, it also
    needs them to belong together, so the coast runs where one theme gives way to another. */
export function coastField(dirs: ArrayLike<number>, w: number, h: number, out = new Uint8Array(w * h), themes?: ArrayLike<number>): Uint8Array {
  const n = Math.floor(dirs.length / 3);
  const kin = themes ? cohesion(dirs, themes) : null;
  const together = kin ? new Float32Array(w * h) : null, gaps = kin ? new Float32Array(w * h) : null;
  const coast = coastRadius(n), beta = 3 / coast;
  // tiles further than this add under e^-12 to the blend
  const near = Math.cos(Math.min(Math.PI, 4 * coast));
  for (let j = 0; j < h; j++) {
    const lat = ((j + 0.5) / h - 0.5) * Math.PI;
    const cl = Math.cos(lat), z = Math.sin(lat);
    for (let i = 0; i < w; i++) {
      const lon = ((i + 0.5) / w - 0.5) * 2 * Math.PI;
      const x = cl * Math.cos(lon), y = cl * Math.sin(lon);
      let sum = 0, best = -1, alike = 0;
      for (let k = 0; k < n; k++) {
        const d = x * dirs[k * 3] + y * dirs[k * 3 + 1] + z * dirs[k * 3 + 2];
        if (d > best) best = d;
        if (d > near) {
          const wgt = Math.exp(-beta * Math.acos(Math.min(1, d)));
          sum += wgt;
          if (kin) alike += wgt * kin[k];
        }
      }
      const dist = sum > 0 ? -Math.log(sum) / beta : Math.acos(Math.max(-1, Math.min(1, best)));
      const v = 0.5 - (dist - coast) / (5 * coast);
      if (together && gaps) { together[j * w + i] = sum > 0 ? alike / sum : 0; gaps[j * w + i] = v; }
      else out[j * w + i] = Math.round(255 * Math.max(0, Math.min(1, v)));
    }
  }
  if (!together || !gaps) return out;
  const { shore, high } = seaLevel(together, w, h, LAND_SHARE);
  const span = Math.max(1e-3, high - shore);
  for (let c = 0; c < out.length; c++) {
    const v = Math.min(gaps[c], 0.5 + (0.5 * (together[c] - shore)) / span);
    out[c] = Math.round(255 * Math.max(0, Math.min(1, v)));
  }
  return out;
}
