import { expect, test } from "vitest";
import { coastField } from "./coast";

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
