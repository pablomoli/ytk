import { expect, test, vi } from "vitest";
import { pixelateSwap } from "./pixelateSwap";

/* A surface with no dimensions cannot be photographed, so the wipe is skipped
   and the swap still happens. */
test("a surface with no dimensions swaps without an overlay", () => {
  const canvas = document.createElement("canvas");
  canvas.width = 0;
  canvas.height = 0;
  document.body.appendChild(canvas);

  const swap = vi.fn();
  pixelateSwap(canvas, swap);

  expect(swap).toHaveBeenCalledTimes(1);
  expect(document.querySelector(".pixelate-overlay")).toBeNull();
  canvas.remove();
});

test("a real surface freezes a frame over the swap, then clears it", async () => {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  document.body.appendChild(canvas);

  const swap = vi.fn();
  pixelateSwap(canvas, swap, { duration: 0.05 });

  expect(swap).toHaveBeenCalledTimes(1);
  expect(document.querySelector(".pixelate-overlay")).not.toBeNull();

  await vi.waitFor(() => expect(document.querySelector(".pixelate-overlay")).toBeNull(), {
    timeout: 2000,
  });
  canvas.remove();
});
