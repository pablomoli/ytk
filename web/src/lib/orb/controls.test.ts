import { expect, test } from "vitest";
import { createControls, PITCH_MAX, SENS } from "./controls";

test("drag maps pixel deltas to yaw/pitch at SENS", () => {
  const c = createControls();
  c.down(100, 100);
  c.move(200, 100); // 100px right
  c.up();
  // settle the spring
  let out = { yaw: 0, pitch: 0 };
  for (let i = 0; i < 600; i++) out = c.step(1 / 60);
  expect(out.yaw).toBeCloseTo(100 * SENS, 3);
  expect(out.pitch).toBeCloseTo(0, 5);
});

test("pitch clamps at +-75deg", () => {
  const c = createControls();
  c.down(0, 0);
  c.move(0, 100000);
  c.up();
  let out = { yaw: 0, pitch: 0 };
  for (let i = 0; i < 600; i++) out = c.step(1 / 60);
  expect(Math.abs(out.pitch)).toBeLessThanOrEqual(PITCH_MAX + 1e-6);
});

test("release keeps momentum then settles (inertia)", () => {
  const c = createControls();
  c.down(0, 0);
  for (let i = 1; i <= 5; i++) {
    c.move(i * 20, 0);
    c.step(1 / 60); // velocity accumulates between moves
  }
  c.up();
  const atRelease = c.step(1 / 60).yaw;
  for (let i = 0; i < 120; i++) c.step(1 / 60);
  const later = c.step(1 / 60).yaw;
  expect(later).toBeGreaterThan(atRelease); // coasted past the release point
  const settled = (() => { let o = c.step(1 / 60); for (let i = 0; i < 900; i++) o = c.step(1 / 60); return o; })();
  const next = c.step(1 / 60);
  expect(Math.abs(next.yaw - settled.yaw)).toBeLessThan(1e-4); // spring at rest
});

test("tap vs drag threshold at 6px travel", () => {
  const c = createControls();
  c.down(10, 10);
  c.move(13, 12); // ~3.6px
  expect(c.up().tap).toBe(true);
  c.down(10, 10);
  c.move(16, 14); // ~7.2px
  expect(c.up().tap).toBe(false);
});

test("setTarget overrides pointer state for the focus tween", () => {
  const c = createControls();
  c.setTarget(1.0, 0.5);
  let out = { yaw: 0, pitch: 0 };
  for (let i = 0; i < 600; i++) out = c.step(1 / 60);
  expect(out.yaw).toBeCloseTo(1.0, 3);
  expect(out.pitch).toBeCloseTo(0.5, 3);
});
