import { expect, test } from "vitest";
import { pullSummary, pullTotal, pullingLabel } from "./pullStatus";

test("names what is being pulled rather than saying 'loading'", () => {
  expect(pullingLabel(["instagram"])).toBe("pulling instagram...");
  expect(pullingLabel(["instagram", "reddit"])).toBe("pulling instagram and reddit...");
  expect(pullingLabel(["a", "b", "c"])).toBe("pulling 3 sources...");
  expect(pullingLabel()).toBe("pulling all sources...");
  expect(pullingLabel([])).toBe("pulling all sources...");
});

test("reports what each source actually returned", () => {
  expect(pullSummary({ instagram: 3, tiktok: 1, youtube: 0 })).toBe("instagram +3 · tiktok +1");
});

/* Found-nothing and did-not-run look identical from outside and mean opposite
   things: one is an empty source, the other is the hub declining to hammer it. */
test("distinguishes an empty pull from a cadence skip", () => {
  expect(pullSummary({ instagram: 0, youtube: 0 })).toBe("nothing new");
  expect(pullSummary({ skipped: true, skipped_sources: ["instagram"] })).toBe(
    "skipped — pulled too recently",
  );
});

test("surfaces a failure when nothing came back", () => {
  expect(pullSummary({ errors: ["instagram: login required"] })).toBe(
    "failed — instagram: login required",
  );
});

/* A partial failure must not be swallowed by a successful-looking count. */
test("still flags failures alongside a partial success", () => {
  expect(pullSummary({ instagram: 2, errors: ["reddit: 429"] })).toBe("instagram +2 (1 failed)");
});

test("returns nothing before a pull has run", () => {
  expect(pullSummary(undefined)).toBe("");
});

test("totals the per-source counts", () => {
  expect(pullTotal({ instagram: 3, tiktok: 1, errors: ["x"] })).toBe(4);
  expect(pullTotal({})).toBe(0);
  expect(pullTotal(undefined)).toBe(0);
});
