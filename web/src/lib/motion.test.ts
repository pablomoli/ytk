import { expect, test } from "vitest";
import { DUR, HOUSE_EASE, gsap, reducedMotion } from "./motion";

test("house defaults are wired", () => {
  expect(HOUSE_EASE).toBe("house");
  expect(DUR).toEqual({ base: 0.18, morph: 0.3, wipe: 0.4, reveal: 0.6 });
  expect(gsap.defaults().duration).toBe(0.18);
  expect(typeof reducedMotion()).toBe("boolean");
});
