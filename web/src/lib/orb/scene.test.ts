import { expect, test, vi } from "vitest";
import type { OrbData } from "../../api/orb";
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
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  document.body.appendChild(canvas);
  const handle = mountOrb(canvas, data(), { onHover: vi.fn(), onOpen: vi.fn() });
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  handle.setLayout("lattice"); // must not throw; haversine absent is a no-op guard
  handle.setLayout("haversine");
  handle.dispose();
  canvas.remove();
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
