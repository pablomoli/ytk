import { afterEach, expect, test, vi } from "vitest";
import { observeStickyTop, stickyTopPx } from "./stickyTop";

afterEach(() => {
  document.body.innerHTML = "";
  document.documentElement.style.removeProperty("--sticky-top");
  vi.unstubAllGlobals();
});

test("sums the measured nav/pad pairs", () => {
  expect(stickyTopPx(84, 18)).toBe(102);
  expect(stickyTopPx(115, 18)).toBe(133);
  expect(stickyTopPx(102, 16)).toBe(118);
  expect(stickyTopPx(129, 16)).toBe(145);
  expect(stickyTopPx(237, 16)).toBe(253);
});

test("clamps NaN inputs to 0", () => {
  expect(stickyTopPx(NaN, 18)).toBe(18);
  expect(stickyTopPx(84, NaN)).toBe(84);
  expect(stickyTopPx(NaN, NaN)).toBe(0);
});

test("clamps negative inputs to 0", () => {
  expect(stickyTopPx(-10, 18)).toBe(18);
  expect(stickyTopPx(84, -5)).toBe(84);
  expect(stickyTopPx(-10, -5)).toBe(0);
});

// jsdom always reports 0 for offsetHeight/getBoundingClientRect, so the
// nav's height is stubbed directly on the element instance. paddingTop
// comes from an inline style, which jsdom's getComputedStyle does honour,
// so that half of the measurement is real rather than stubbed.
function buildHubDom(navHeight: number, bodyPaddingTop: number) {
  const nav = document.createElement("header");
  nav.className = "hub-nav";
  Object.defineProperty(nav, "getBoundingClientRect", {
    configurable: true,
    value: () => ({ height: navHeight }) as DOMRect,
  });

  const body = document.createElement("div");
  body.className = "hub-body";
  body.style.paddingTop = `${bodyPaddingTop}px`;

  document.body.append(nav, body);
  return { nav, body };
}

test("writes --sticky-top when .hub-nav and .hub-body exist", () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
  buildHubDom(84, 18);

  const cleanup = observeStickyTop();

  expect(document.documentElement.style.getPropertyValue("--sticky-top")).toBe("102px");
  expect(cleanup).toBeTypeOf("function");
  expect(() => cleanup()).not.toThrow();
});

test("falls back to a resize listener when ResizeObserver is unavailable", () => {
  vi.stubGlobal("ResizeObserver", undefined);
  const addSpy = vi.spyOn(window, "addEventListener");
  const removeSpy = vi.spyOn(window, "removeEventListener");
  buildHubDom(115, 18);

  const cleanup = observeStickyTop();

  expect(document.documentElement.style.getPropertyValue("--sticky-top")).toBe("133px");
  expect(addSpy).toHaveBeenCalledWith("resize", expect.any(Function));

  cleanup();
  expect(removeSpy).toHaveBeenCalledWith("resize", expect.any(Function));
});

test("does not throw and returns a callable cleanup when the elements are absent", () => {
  const cleanup = observeStickyTop();
  expect(document.documentElement.style.getPropertyValue("--sticky-top")).toBe("");
  expect(cleanup).toBeTypeOf("function");
  expect(() => cleanup()).not.toThrow();
});
