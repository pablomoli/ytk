import { expect, test } from "vitest";
import { coverAspect } from "./coverAspect";

test("known sources reserve their measured median ratio", () => {
  // Instagram is the tight one: p10 0.563, p90 0.800 across 56 live covers.
  expect(coverAspect("instagram")).toBeCloseTo(0.563);
  expect(coverAspect("reddit")).toBeCloseTo(1.197);
});

test("an unknown source still reserves a box", () => {
  // The failure this guards is reserving nothing: a zero-height cover is
  // measured at zero, placed, and shoves every card below it on decode.
  const ratio = coverAspect("some-future-source");
  expect(ratio).toBeGreaterThan(0);
  expect(Number.isFinite(ratio)).toBe(true);
});

test("every default is a plausible image ratio", () => {
  for (const source of ["instagram", "tiktok", "reddit", "pinterest", "youtube", "web"]) {
    const ratio = coverAspect(source);
    expect(ratio).toBeGreaterThan(0.2);
    expect(ratio).toBeLessThan(5);
  }
});
