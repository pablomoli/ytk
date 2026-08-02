import { expect, test, vi } from "vitest";
import type { OrbData } from "../../api/orb";
import { COLS } from "./atlas";
import {
  GLOBE_R_CLOSE,
  GLOBE_R_FAR,
  MAX_FWD,
  mountOrb,
  normalizeWheelDelta,
  restGlobeR,
  wheelDollyOffset,
} from "./scene";

function data(): OrbData {
  return {
    points: [
      { p: "a.md", t: "a", c: "youtube", th: 0, thumb: null },
      { p: "b.md", t: "b", c: "instagram", th: 1, thumb: null },
      { p: "c.md", t: "c", c: "web", th: 0, thumb: null },
    ],
    themes: ["one", "two"],
    sphere: {
      radial: [[0, 0, -1], [1, 0, 0], [0, 1, 0]],
      haversine: null,
      lattice: [[0, 0, 1], [0, -1, 0], [-1, 0, 0]],
      scores: {},
      chosen: "radial",
    },
  };
}

test("mounts, renders one instanced draw, disposes clean", async () => {
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const handle = mountOrb(canvas, data(), { onHover: vi.fn(), onOpen: vi.fn() });
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  // green does not prove the shader linked: three only console.errors GLSL
  // compile/link failures rather than throwing, so a passing test with an
  // unnoticed link error would still reach here
  expect(errSpy).not.toHaveBeenCalled();
  handle.setLayout("lattice"); // must not throw; haversine absent is a no-op guard
  handle.setLayout("haversine");
  handle.dispose();
  canvas.remove();
  errSpy.mockRestore();
});

test("clamps instance count to atlas capacity and warns instead of silently dropping", async () => {
  const cap = COLS * COLS;
  const overflow = cap + 1;
  const points: OrbData["points"] = Array.from({ length: overflow }, (_, i) => ({
    p: `${i}.md`,
    t: `${i}`,
    c: "web",
    th: 0,
    thumb: null,
  }));
  const radial = Array.from({ length: overflow }, () => [0, 0, -1]);
  const overflowData: OrbData = {
    points,
    themes: ["one"],
    sphere: { radial, haversine: null, lattice: radial, scores: {}, chosen: "radial" },
  };
  const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const handle = mountOrb(canvas, overflowData, { onHover: vi.fn(), onOpen: vi.fn() });
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  expect(warnSpy).toHaveBeenCalledTimes(1);
  expect(warnSpy.mock.calls[0][0]).toContain(String(cap));
  handle.dispose();
  canvas.remove();
  warnSpy.mockRestore();
});

test("setLayout warns and keeps current centers when the target array is shorter than the point count", async () => {
  const d = data();
  d.sphere.lattice = [[0, 0, 1], [0, -1, 0]]; // truncated: fewer rows than points
  const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const handle = mountOrb(canvas, d, { onHover: vi.fn(), onOpen: vi.fn() });
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  expect(() => handle.setLayout("lattice")).not.toThrow();
  expect(warnSpy).toHaveBeenCalledTimes(1);
  expect(warnSpy.mock.calls[0][0]).toContain("lattice");
  handle.dispose();
  canvas.remove();
  warnSpy.mockRestore();
});

test("focus fires onOpen with a viewport rect (reduced motion path)", async () => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never; // reducedMotion
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const onOpen = vi.fn();
  const handle = mountOrb(canvas, data(), { onHover: vi.fn(), onOpen });
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  handle.focus(0);
  await vi.waitFor(() => expect(onOpen).toHaveBeenCalled());
  const [i, rect] = onOpen.mock.calls[0];
  expect(i).toBe(0);
  expect(rect.width).toBeGreaterThan(0);
  handle.dispose();
  canvas.remove();
});

test("setView(\"globe\") renders without shader errors and disposes clean", async () => {
  const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const handle = mountOrb(canvas, data(), { onHover: vi.fn(), onOpen: vi.fn() });
  handle.setView("globe");
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  expect(errSpy).not.toHaveBeenCalled();
  handle.dispose();
  canvas.remove();
  errSpy.mockRestore();
});

test("wheel delta normalizes across engines: 3 lines (Gecko) ~= 100px (Chromium) per physical tick", () => {
  const gecko = normalizeWheelDelta(3, 1, 800);
  const chromium = normalizeWheelDelta(100, 0, 800);
  expect(Math.abs(gecko - chromium)).toBeLessThan(5); // 3*33=99 vs 100: within a couple units, not orders of magnitude
});

test("wheel delta passes pixel mode through unchanged and scales page mode by viewport height", () => {
  expect(normalizeWheelDelta(42, 0, 800)).toBe(42);
  expect(normalizeWheelDelta(2, 2, 800)).toBe(1600);
});

test("inside-mode wheel dolly offset never exceeds MAX_FWD across the zoom range", () => {
  for (const zoom of [0, 0.25, 0.5, 0.75, 1]) {
    expect(Math.abs(wheelDollyOffset(zoom))).toBeLessThanOrEqual(MAX_FWD + 1e-9);
  }
  // at zoom=1 offset==MAX_FWD; with a unit look direction this is the camera's
  // full position magnitude, and 1 - MAX_FWD = 0.28 > 0.2 (the required bound)
  expect(wheelDollyOffset(1)).toBeCloseTo(MAX_FWD, 6);
  expect(1 - MAX_FWD).toBeGreaterThan(0.2);
});

test("globe orbit radius clamps at [1.30, 4.0]", () => {
  expect(restGlobeR(0)).toBeCloseTo(GLOBE_R_CLOSE, 6);
  expect(restGlobeR(1)).toBeCloseTo(GLOBE_R_FAR, 6);
  expect(GLOBE_R_CLOSE).toBeCloseTo(1.30, 6);
  expect(GLOBE_R_FAR).toBeCloseTo(4.0, 6);
});

test("focus fires onOpen with a positive-width rect in globe view (reduced motion path)", async () => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never; // reducedMotion
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const onOpen = vi.fn();
  const handle = mountOrb(canvas, data(), { onHover: vi.fn(), onOpen });
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  handle.setView("globe");
  handle.focus(0);
  await vi.waitFor(() => expect(onOpen).toHaveBeenCalled());
  const [i, rect] = onOpen.mock.calls[0];
  expect(i).toBe(0);
  expect(rect.width).toBeGreaterThan(0);
  handle.dispose();
  canvas.remove();
});
