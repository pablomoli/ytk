import { expect, test } from "vitest";
import { decay, pushSample, releaseVelocity } from "./mapInertia";
import type { VelocitySample } from "./mapInertia";

test("pushSample drops ALL samples outside the window", () => {
  const buffer: VelocitySample[] = [];
  pushSample(buffer, { x: 0, y: 0, t: 0 });
  pushSample(buffer, { x: 1, y: 0, t: 50 });
  pushSample(buffer, { x: 2, y: 0, t: 200 });
  // both t=0 (200ms old) and t=50 (150ms old) are beyond the 90ms window
  expect(buffer).toEqual([{ x: 2, y: 0, t: 200 }]);
});

test("samples inside the window are all kept", () => {
  const buffer: VelocitySample[] = [];
  pushSample(buffer, { x: 0, y: 0, t: 100 });
  pushSample(buffer, { x: 1, y: 0, t: 150 });
  pushSample(buffer, { x: 2, y: 0, t: 180 });
  expect(buffer).toHaveLength(3);
});

test("releaseVelocity averages displacement over time", () => {
  const buffer: VelocitySample[] = [];
  pushSample(buffer, { x: 0, y: 0, t: 0 });
  pushSample(buffer, { x: 10, y: -5, t: 50 });
  const v = releaseVelocity(buffer);
  expect(v.vx).toBeCloseTo(0.2); // 10px / 50ms
  expect(v.vy).toBeCloseTo(-0.1);
});

test("releaseVelocity is zero with fewer than 2 samples", () => {
  expect(releaseVelocity([])).toEqual({ vx: 0, vy: 0 });
  expect(releaseVelocity([{ x: 1, y: 1, t: 1 }])).toEqual({ vx: 0, vy: 0 });
});

test("decay is exponential and never overshoots", () => {
  expect(decay(1, 0)).toBe(1);
  expect(decay(1, 0.25)).toBeCloseTo(Math.exp(-1));
  expect(decay(-2, 10)).toBeCloseTo(0, 5);
});
