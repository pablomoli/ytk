import { describe, expect, it } from "vitest";
import { PerspectiveCamera } from "three";
import { pickPlanet } from "./pick";

describe("pickPlanet", () => {
  const cam = new PerspectiveCamera(60, 1, 0.01, 10);
  cam.position.set(0, 0, 3);
  cam.lookAt(0, 0, 0);
  cam.updateMatrixWorld();
  const planets = [
    { pos: [0, 0, 1] as [number, number, number], radius_deg: 12 },
    { pos: [0, 0, -1] as [number, number, number], radius_deg: 12 },
  ];
  it("hits the near planet at screen center", () => {
    expect(pickPlanet(0, 0, cam, planets)).toBe(0);
  });
  it("misses off to the side", () => {
    expect(pickPlanet(0.95, 0.95, cam, planets)).toBeNull();
  });
});
