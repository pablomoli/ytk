import { expect, test } from "vitest";
import { decay, pushSample, releaseVelocity } from "./mapInertia";
import type { VelocitySample } from "./mapInertia";

test("pushSample drops samples outside the window", () => {
  const buffer: VelocitySample[] = [];
  pushSample(buffer, { x: 0, y: 0, t: 0 });
  pushSample(buffer, { x: 1, y: 0, t: 50 });
  pushSample(buffer, { x: 2, y: 0, t: 200 });
  expect(buffer).toHaveLength(2); // t=0 dropped (200-0 > 90)
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
