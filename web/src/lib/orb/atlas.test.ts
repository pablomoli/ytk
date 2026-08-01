import { expect, test } from "vitest";
import type { OrbPoint } from "../../api/orb";
import { ATLAS_SIZE, buildAtlas, COLS, themeColor, TILE, uvRect } from "./atlas";

test("uvRect flips v for three.js bottom-left origin", () => {
  // slot 0: canvas top-left tile -> UV origin at its BOTTOM edge
  expect(uvRect(0)).toEqual({ u: 0, v: 1 - TILE / ATLAS_SIZE, s: TILE / ATLAS_SIZE });
  // slot 33: row 1, col 1
  expect(uvRect(33)).toEqual({
    u: TILE / ATLAS_SIZE,
    v: 1 - (2 * TILE) / ATLAS_SIZE,
    s: TILE / ATLAS_SIZE,
  });
  expect(COLS).toBe(ATLAS_SIZE / TILE);
});

test("themeColor is a stable hsl ramp", () => {
  expect(themeColor(0, 17)).toBe(themeColor(0, 17));
  expect(themeColor(0, 17)).not.toBe(themeColor(1, 17));
});

test("buildAtlas paints placeholders immediately and resolves idle", async () => {
  const points: OrbPoint[] = [
    { p: "a.md", t: "a", c: "youtube", th: 0, thumb: null },
    { p: "b.md", t: "b", c: "instagram", th: 1, thumb: "missing/nope.jpg" },
  ];
  const atlas = buildAtlas(points, 17, () => {});
  const canvas = atlas.texture.image as HTMLCanvasElement;
  expect(canvas.width).toBe(ATLAS_SIZE);
  const px = canvas.getContext("2d")!.getImageData(TILE / 2, TILE / 2, 1, 1).data;
  expect(px[3]).toBe(255); // placeholder painted, not transparent
  await atlas.idle; // missing image resolves (failure keeps placeholder)
  atlas.dispose();
});
