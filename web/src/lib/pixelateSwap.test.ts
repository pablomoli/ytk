import { expect, test, vi } from "vitest";
import { pixelateSwap } from "./pixelateSwap";

test("swap always runs; degraded environments get no overlay", () => {
  // jsdom canvas has no real 2d context data, width/height 0 -> degraded path
  const canvas = document.createElement("canvas");
  document.body.appendChild(canvas);
  const swap = vi.fn();
  pixelateSwap(canvas, swap);
  expect(swap).toHaveBeenCalledTimes(1);
  expect(document.querySelector(".pixelate-overlay")).toBeNull();
});
