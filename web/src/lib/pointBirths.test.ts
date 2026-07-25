import { describe, expect, it } from "vitest";
import type { MapPoint } from "../api/map";
import { pointBirths } from "./mapRenderer";

const pt = (d?: string): MapPoint => ({ d }) as unknown as MapPoint;

describe("pointBirths", () => {
  it("spans 0..1 across the dated corpus", () => {
    const b = pointBirths(["2020-01-01", "2022-01-01", "2026-01-01"].map(pt));
    expect(b[0]).toBe(0);
    expect(b[2]).toBe(1);
  });

  it("ranks by order, not by elapsed time", () => {
    // The whole reason for quantiles: these three dates are wildly uneven in
    // real time, and the middle one must still land at the midpoint.
    const b = pointBirths(["2018-01-01", "2026-01-01", "2026-01-02"].map(pt));
    expect(b[1]).toBeCloseTo(0.5, 10);
  });

  it("marks undated points with the -1 sentinel", () => {
    const b = pointBirths([pt("2026-01-01"), pt(), pt("2026-06-01")]);
    expect(b[1]).toBe(-1);
  });

  it("keeps undated points out of the ranking entirely", () => {
    // Undated notes are whole categories; letting them occupy ranks would
    // shift every real note's position by a bias that varies with category.
    const withGaps = pointBirths([pt("2020-01-01"), pt(), pt(), pt("2026-01-01")]);
    const without = pointBirths([pt("2020-01-01"), pt("2026-01-01")]);
    expect([withGaps[0], withGaps[3]]).toEqual([without[0], without[1]]);
  });

  it("gives same-day notes the same birth so they arrive together", () => {
    const b = pointBirths([pt("2026-01-01"), pt("2026-01-01"), pt("2026-06-01")]);
    expect(b[0]).toBe(b[1]);
  });

  it("degrades safely when there is nothing to rank", () => {
    expect(pointBirths([])).toEqual([]);
    expect(pointBirths([pt("2026-01-01")])).toEqual([-1]);
    expect(pointBirths([pt(), pt()])).toEqual([-1, -1]);
  });

  it("never returns a value that would hide a dated note at clock=1", () => {
    const dates = Array.from(
      { length: 50 },
      (_, i) => `2026-${String((i % 12) + 1).padStart(2, "0")}-01`,
    );
    for (const b of pointBirths(dates.map(pt))) {
      expect(b).toBeGreaterThanOrEqual(0);
      expect(b).toBeLessThanOrEqual(1);
    }
  });
});
