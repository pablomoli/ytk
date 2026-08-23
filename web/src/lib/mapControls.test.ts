import { describe, expect, it } from "vitest";
import {
  initialMapControls,
  mapControlsReducer,
  resetMapControls,
  visibleMapLayers,
} from "./mapControls";

describe("mapControlsReducer", () => {
  it("turning terrain on clears incompatible volume layers", () => {
    const start = {
      ...initialMapControls(),
      layers: { terrain: false, web: true, fog: true, shell: true },
    };

    expect(mapControlsReducer(start, { type: "toggle-layer", layer: "terrain" }).layers).toEqual({
      terrain: true,
      web: false,
      fog: false,
      shell: false,
    });
  });

  it("turning web or fog on selects 3D and clears terrain", () => {
    const flatTerrain = {
      ...initialMapControls(),
      projection: "2d" as const,
      layers: { terrain: true, web: false, fog: false, shell: false },
    };

    const web = mapControlsReducer(flatTerrain, { type: "toggle-layer", layer: "web" });
    expect(web.projection).toBe("3d");
    expect(web.layers).toEqual({ terrain: false, web: true, fog: false, shell: false });

    const fog = mapControlsReducer(flatTerrain, { type: "toggle-layer", layer: "fog" });
    expect(fog.projection).toBe("3d");
    expect(fog.layers).toEqual({ terrain: false, web: false, fog: true, shell: false });
  });

  it("allows web and fog together while shell always implies fog", () => {
    const web = mapControlsReducer(initialMapControls(), { type: "toggle-layer", layer: "web" });
    const fog = mapControlsReducer(web, { type: "toggle-layer", layer: "fog" });
    expect(fog.layers.web).toBe(true);
    expect(fog.layers.fog).toBe(true);

    const shell = mapControlsReducer(initialMapControls(), {
      type: "toggle-layer",
      layer: "shell",
    });
    expect(shell.layers.fog).toBe(true);
    expect(shell.layers.shell).toBe(true);
    expect(shell.projection).toBe("3d");
  });

  it("selecting 2D clears layers that cannot render there", () => {
    const volume = {
      ...initialMapControls(),
      layers: { terrain: false, web: true, fog: true, shell: true },
    };

    expect(mapControlsReducer(volume, { type: "set-projection", projection: "2d" })).toMatchObject({
      projection: "2d",
      layers: { terrain: false, web: false, fog: false, shell: false },
    });
  });

  it("reset returns the complete control surface to its neutral state", () => {
    const changed = {
      view: "content" as const,
      projection: "2d" as const,
      filters: { signal: true, recent: true, media: true, time: true },
      layers: { terrain: true, web: false, fog: false, shell: false },
      road: true,
    };

    expect(resetMapControls()).toEqual(initialMapControls());
    expect(mapControlsReducer(changed, { type: "reset" })).toEqual(initialMapControls());
  });
});

it("derives layer availability from the active layout", () => {
  const terrain = { h: 1, levels: [], contours: [], ridges: [] };
  const fog = { h: 1, splats: [] };
  expect(visibleMapLayers({ terrain, fog })).toEqual({
    terrain: true,
    web: false,
    fog: true,
    shell: true,
  });
});
