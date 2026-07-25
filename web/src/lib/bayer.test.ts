import { expect, test } from "vitest";
import { BAYER8, ditherOrder, hashString } from "./bayer";

test("BAYER8 is a permutation of 0..63", () => {
  const flat = BAYER8.flat();
  expect(flat).toHaveLength(64);
  expect([...flat].sort((a, b) => a - b)).toEqual(Array.from({ length: 64 }, (_, i) => i));
});

test("hashString is deterministic and non-negative", () => {
  expect(hashString("sources/youtube/x.md")).toBe(hashString("sources/youtube/x.md"));
  expect(hashString("a")).not.toBe(hashString("b"));
  expect(hashString("anything")).toBeGreaterThanOrEqual(0);
});

test("ditherOrder is a deterministic permutation, seed-sensitive", () => {
  const a = ditherOrder(10, 6, 7);
  expect([...a].sort((x, y) => x - y)).toEqual(Array.from({ length: 60 }, (_, i) => i));
  expect(ditherOrder(10, 6, 7)).toEqual(a);
  expect(ditherOrder(10, 6, 8)).not.toEqual(a);
});
