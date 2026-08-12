import { describe, expect, it, vi } from "vitest";
import { mountGalaxy } from "./scene";
import type { GalaxyData } from "../../api/galaxy";

const data: GalaxyData = {
  epoch: "v2",
  k_deg: 3,
  planets: [0, 1].map((i) => ({
    theme: i, label: `p${i}`, n: 20, activity: 0.5, cohesion: 0.6,
    cls: "V", hue: "#ffb08a", pos: i ? [0, 1, 0] : [1, 0, 0], radius_deg: 8,
    tex: `${i}.png`, hue_shift_deg: i ? 210 : 0, land_frac: 0.64, median_age_days: 40,
    rings: { earned: i === 0, partners: i === 0 ? [{ theme: 1, z: 5 }] : [] },
    spin: { earned: false, side: null, median_age_days: 40 },
    moons: [],
  })),
};

describe("mountGalaxy", () => {
  it("mounts, reports hover/visit, and disposes clean", () => {
    const canvas = document.createElement("canvas");
    Object.defineProperty(canvas, "clientWidth", { value: 640 });
    Object.defineProperty(canvas, "clientHeight", { value: 480 });
    const cb = { onHover: vi.fn(), onVisit: vi.fn(), onMoonOpen: vi.fn() };
    const handle = mountGalaxy(canvas, data, cb);
    handle.visit(1);
    expect(cb.onVisit).toHaveBeenCalledWith(1);
    handle.overview();
    expect(cb.onVisit).toHaveBeenCalledWith(null);
    handle.dispose(); // must not throw, must cancel the raf loop
  });

  // three console.errors GLSL compile/link failures rather than throwing, and
  // the test above never reaches a frame — a silent shader break would pass it
  it("renders frames with rings and moons without shader errors", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const withMoons: GalaxyData = {
      ...data,
      planets: data.planets.map((p, i) =>
        i === 1 ? { ...p, moons: [{ size: 4, path: "a.md", title: "a", thumb: null }] } : p,
      ),
    };
    const canvas = document.createElement("canvas");
    canvas.width = 400;
    canvas.height = 300;
    document.body.appendChild(canvas);
    const cb = { onHover: vi.fn(), onVisit: vi.fn(), onMoonOpen: vi.fn() };
    const handle = mountGalaxy(canvas, withMoons, cb);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    expect(errSpy).not.toHaveBeenCalled();
    handle.visit(0);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    expect(errSpy).not.toHaveBeenCalled();
    handle.dispose();
    canvas.remove();
    errSpy.mockRestore();
  });
});
