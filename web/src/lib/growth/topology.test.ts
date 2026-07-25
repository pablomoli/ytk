import { expect, test } from "vitest";
import { DEFAULT_CONSTRAINTS } from "./dna";
import { generateTopology } from "./topology";

const params = { density: 0.6, motion: 0.3, granularity: 0.5, asymmetry: 0.6 };

test("deterministic for a given seed key", () => {
  expect(generateTopology("th-1", params, DEFAULT_CONSTRAINTS)).toEqual(
    generateTopology("th-1", params, DEFAULT_CONSTRAINTS),
  );
});

test("different keys give different shapes", () => {
  const a = generateTopology("th-1", params, DEFAULT_CONSTRAINTS);
  const b = generateTopology("th-2", params, DEFAULT_CONSTRAINTS);
  expect(a).not.toEqual(b);
});

test("all nodes in frame, radii sane, parents valid", () => {
  const nodes = generateTopology("th-3", params, DEFAULT_CONSTRAINTS);
  expect(nodes.length).toBeGreaterThan(6);
  for (const [i, n] of nodes.entries()) {
    expect(n.x).toBeGreaterThan(0.05);
    expect(n.x).toBeLessThan(0.95);
    expect(n.y).toBeGreaterThan(0.05);
    expect(n.y).toBeLessThan(0.95);
    expect(n.radius).toBeGreaterThan(0.015);
    expect(n.radius).toBeLessThan(0.2);
    expect(n.parent).toBeLessThan(i);
  }
});

test("silhouette is asymmetric: centroid offset from center", () => {
  const nodes = generateTopology("th-4", { ...params, asymmetry: 0.9 }, DEFAULT_CONSTRAINTS);
  const cx = nodes.reduce((s, n) => s + n.x, 0) / nodes.length;
  const cy = nodes.reduce((s, n) => s + n.y, 0) / nodes.length;
  expect(Math.hypot(cx - 0.5, cy - 0.5)).toBeGreaterThan(0.03);
});

test("density raises node count", () => {
  const sparse = generateTopology("th-5", { ...params, density: 0.2 }, DEFAULT_CONSTRAINTS);
  const dense = generateTopology("th-5", { ...params, density: 0.95 }, DEFAULT_CONSTRAINTS);
  expect(dense.length).toBeGreaterThan(sparse.length);
});
