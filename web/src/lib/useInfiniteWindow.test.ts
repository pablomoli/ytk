import { renderHook, act } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { nextCount, useInfiniteWindow } from "./useInfiniteWindow";

// Capture the IntersectionObserver callback so a test can fire it and grow the
// window past `step` — without that, count never exceeds step and the reset
// bug is unobservable (a reset-to-step is a no-op when count is already step).
let observerCb: ((entries: { isIntersecting: boolean }[]) => void) | null = null;
vi.stubGlobal(
  "IntersectionObserver",
  class {
    constructor(cb: (entries: { isIntersecting: boolean }[]) => void) {
      observerCb = cb;
    }
    observe() {}
    disconnect() {}
    unobserve() {}
  },
);

test("nextCount clamps to total", () => {
  expect(nextCount(60, 70, 60)).toBe(70);
});

test("a poll refetch (new array identity, same resetKey) preserves the grown window", () => {
  const { result, rerender } = renderHook(
    ({ items }: { items: string[] }) => useInfiniteWindow(items, 2, "all"),
    { initialProps: { items: ["a", "b", "c", "d", "e"] } },
  );
  // attach the sentinel so the hook builds the observer, then grow the window
  act(() => result.current.sentinelRef(document.createElement("div")));
  expect(result.current.visible).toEqual(["a", "b"]);
  act(() => observerCb?.([{ isIntersecting: true }]));
  expect(result.current.visible).toEqual(["a", "b", "c", "d"]); // grown 2 -> 4

  // the bug: a background poll returns the same content in a fresh array, and
  // an effect keyed on items identity snapped the window back to the top.
  rerender({ items: ["a", "b", "c", "d", "e", "f"] });
  expect(result.current.visible).toEqual(["a", "b", "c", "d"]); // window preserved
});

test("a resetKey change (filter switch) resets the window to step", () => {
  const { result, rerender } = renderHook(
    ({ key }: { key: string }) => useInfiniteWindow(["a", "b", "c", "d", "e"], 2, key),
    { initialProps: { key: "all" } },
  );
  act(() => result.current.sentinelRef(document.createElement("div")));
  act(() => observerCb?.([{ isIntersecting: true }]));
  expect(result.current.visible).toEqual(["a", "b", "c", "d"]); // grown
  rerender({ key: "youtube" });
  expect(result.current.visible).toEqual(["a", "b"]); // filter change resets
});
