import { describe, expect, it } from "vitest";
import { equirectUv, ringNormal, slerp, spinRadPerSec, standoff, worldRadius } from "./math";

const len = (v: number[]) => Math.hypot(...v);

describe("galaxy math", () => {
  it("worldRadius keeps angular size honest", () => {
    expect(worldRadius(12)).toBeCloseTo(Math.sin((12 * Math.PI) / 180));
  });
  it("spin clamps 20..600 s/rot and falls back to the population median", () => {
    expect(spinRadPerSec(24, 55)).toBeCloseTo((2 * Math.PI) / 24);
    expect(spinRadPerSec(5, 55)).toBeCloseTo((2 * Math.PI) / 20);
    expect(spinRadPerSec(900, 55)).toBeCloseTo((2 * Math.PI) / 600);
    expect(spinRadPerSec(null, 55)).toBeCloseTo((2 * Math.PI) / 55);
  });
  it("equirectUv matches the bake orientation", () => {
    expect(equirectUv([1, 0, 0])).toEqual([0.5, 0.5]);       // lon 0, lat 0
    expect(equirectUv([0, 0, 1])[1]).toBeCloseTo(1.0);        // north pole -> top row
    expect(equirectUv([-1, 0, 0])[0]).toBeCloseTo(1.0);       // lon pi -> right edge
  });
  it("ringNormal tilts from radial toward the partner", () => {
    const n = ringNormal([1, 0, 0], [0, 1, 0]);
    expect(len(n)).toBeCloseTo(1);
    expect(n[0]).toBeCloseTo(Math.cos(Math.PI / 6));
    expect(n[1]).toBeCloseTo(Math.sin(Math.PI / 6));
  });
  it("standoff sits outside the planet along its radial", () => {
    const s = standoff([0, 0, 1], 12);
    expect(s[2]).toBeCloseTo(1 + 3.2 * worldRadius(12));
  });
  it("slerp stays on the unit sphere", () => {
    const m = slerp([1, 0, 0], [0, 1, 0], 0.5);
    expect(len(m)).toBeCloseTo(1);
    expect(m[0]).toBeCloseTo(m[1]);
  });
});
