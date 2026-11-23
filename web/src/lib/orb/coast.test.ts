import { expect, test } from "vitest";
import { coastField, driftField } from "./coast";

const W = 64, H = 32;
// texel under a direction, in the field's own frame (z up, row 0 at the south pole)
const at = (f: Uint8Array, x: number, y: number, z: number) => {
  const i = Math.min(W - 1, Math.floor((Math.atan2(y, x) / (2 * Math.PI) + 0.5) * W));
  const j = Math.min(H - 1, Math.floor((Math.asin(z) / Math.PI + 0.5) * H));
  return f[j * W + i];
};

test("land sits under the tiles and moves when they do", () => {
  const cluster = (cx: number, cy: number) => {
    const out: number[] = [];
    for (let k = 0; k < 40; k++) {
      const a = cx + 0.02 * (k % 7), b = cy + 0.02 * Math.floor(k / 7);
      out.push(Math.cos(b) * Math.cos(a), Math.cos(b) * Math.sin(a), Math.sin(b));
    }
    return out;
  };
  const east = coastField(cluster(0, 0), W, H);
  expect(at(east, 1, 0, 0)).toBeGreaterThan(128); // land under the cluster
  expect(at(east, -1, 0.01, 0)).toBeLessThan(128); // sea on the far side
  const west = coastField(cluster(Math.PI - 0.1, 0), W, H);
  expect(at(west, 1, 0, 0)).toBeLessThan(128);
  expect(at(west, -1, 0.01, 0)).toBeGreaterThan(128);
});

test("each made-up shape has both land and sea, and no two are the same", () => {
  let seed = 7;
  const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const land = (f: Uint8Array) => f.reduce((a, v) => a + (v > 128 ? 1 : 0), 0) / f.length;
  const a = driftField(rand, W, H), b = driftField(rand, W, H);
  for (const f of [a, b]) { expect(land(f)).toBeGreaterThan(0.2); expect(land(f)).toBeLessThan(0.8); }
  let moved = 0;
  for (let c = 0; c < a.length; c++) if (a[c] > 128 !== b[c] > 128) moved++;
  expect(moved / a.length).toBeGreaterThan(0.1);
});
