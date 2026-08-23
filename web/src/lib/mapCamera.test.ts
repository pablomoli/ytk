import { describe, expect, it } from "vitest";
import { DEFAULT_MAP_CAMERA, centerZoom, resetCameraState } from "./mapCamera";

describe("map camera commands", () => {
  it("center-anchored zoom preserves the world point at screen center", () => {
    expect(centerZoom({ scale: 2, offset: [0.25, -0.5] }, 1.5)).toEqual({
      scale: 3,
      offset: [0.375, -0.75],
    });
  });

  it("clamps zoom to renderer bounds", () => {
    expect(centerZoom({ scale: 10, offset: [0, 0] }, 2).scale).toBe(12);
    expect(centerZoom({ scale: 0.5, offset: [0, 0] }, 0.1).scale).toBe(0.3);
  });

  it("home restores camera only to the canonical pose", () => {
    expect(resetCameraState()).toEqual(DEFAULT_MAP_CAMERA);
  });
});
