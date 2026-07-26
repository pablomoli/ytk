import { expect, test } from "vitest";
import { capturedLabel } from "./captured";

test("formats a plain calendar date", () => {
  expect(capturedLabel("2026-01-06")).toBe("6 Jan 2026");
  expect(capturedLabel("2026-12-31")).toBe("31 Dec 2026");
});

/* A bare date parses as UTC midnight, so a local-zone render would show the
   day before for anyone west of Greenwich. The label must not drift. */
test("does not shift the day", () => {
  expect(capturedLabel("2026-03-01")).toBe("1 Mar 2026");
});

test("accepts a full timestamp and keeps only the date", () => {
  expect(capturedLabel("2026-01-06T23:45:00Z")).toBe("6 Jan 2026");
});

test("returns empty for missing or unusable values", () => {
  expect(capturedLabel(undefined)).toBe("");
  expect(capturedLabel(null)).toBe("");
  expect(capturedLabel("")).toBe("");
  expect(capturedLabel("yesterday")).toBe("");
  expect(capturedLabel("2026-13-01")).toBe("");
});
