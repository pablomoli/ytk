import { expect, test } from "vitest";
import { kmeansPalette } from "./palette";

function block(r: number, g: number, b: number, n: number): number[] {
  return Array.from({ length: n }, () => [r, g, b, 255]).flat();
}

test("recovers dominant colors, luminance-ascending for render roles", () => {
  const pixels = new Uint8ClampedArray([
    ...block(200, 40, 30, 600),
    ...block(20, 30, 40, 300),
    ...block(240, 230, 210, 100),
  ]);
  const palette = kmeansPalette(pixels, 3);
  expect(palette).toHaveLength(3);
  for (const c of palette) expect(c).toMatch(/^#[0-9a-f]{6}$/);
  // Darkest cluster first (deep field), brightest last (membrane).
  const lum = (c: string) =>
    0.2126 * parseInt(c.slice(1, 3), 16) +
    0.7152 * parseInt(c.slice(3, 5), 16) +
    0.0722 * parseInt(c.slice(5, 7), 16);
  expect(lum(palette[0])).toBeLessThan(lum(palette[1]));
  expect(lum(palette[1])).toBeLessThan(lum(palette[2]));
});

test("deterministic across calls", () => {
  const pixels = new Uint8ClampedArray(block(10, 200, 100, 500).concat(block(90, 10, 200, 500)));
  expect(kmeansPalette(pixels, 4)).toEqual(kmeansPalette(pixels, 4));
});

test("handles fewer distinct colors than k", () => {
  const pixels = new Uint8ClampedArray(block(50, 50, 50, 64));
  const palette = kmeansPalette(pixels, 5);
  expect(palette).toHaveLength(5);
});
