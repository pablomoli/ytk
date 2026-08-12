import { describe, expect, it } from "vitest";
import { BG, CLASS_HUES, DIM, GOLD, planetColor, punch, saturation } from "./palette";

describe("palette mirror", () => {
  it("carries the plot_assets constants", () => {
    expect(BG).toBe("#08080a");
    expect(GOLD).toBe("#f2b950");
    expect(DIM).toBe("#3a3a42");
    expect(CLASS_HUES.V).toBe("#ffb08a");
    expect(CLASS_HUES.III).toBe("#5a8cff");
  });
  it("punch lifts dim values (gamma 0.72)", () => {
    expect(punch(0.17)).toBeCloseTo(0.17 ** 0.72, 10);
    expect(punch(-1)).toBe(0);
    expect(punch(2)).toBe(1);
  });
  it("saturation spans 0.3..1.0 over the population", () => {
    expect(saturation(0.2, 0.2, 0.8)).toBeCloseTo(0.3);
    expect(saturation(0.8, 0.2, 0.8)).toBeCloseTo(1.0);
    expect(saturation(0.5, 0.5, 0.5)).toBe(1.0);
  });
  it("planetColor mixes hue toward DIM as cohesion drops", () => {
    const full = planetColor("#ffb08a", 1.0);
    const low = planetColor("#ffb08a", 0.3);
    expect(full[0]).toBeCloseTo(0xff / 255, 5);
    expect(low[0]).toBeLessThan(full[0]);
  });
});
