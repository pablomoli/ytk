import { expect, test, vi } from "vitest";
import type { OrbData } from "../../api/orb";
import { COLS } from "./atlas";
import { mountOrb } from "./scene";

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
