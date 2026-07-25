import { expect, test } from "vitest";
import { CURSOR_PREF, getPref, setPref } from "./prefs";

test("prefs round-trip through localStorage, default false", () => {
  expect(getPref(CURSOR_PREF)).toBe(false);
  setPref(CURSOR_PREF, true);
  expect(getPref(CURSOR_PREF)).toBe(true);
  setPref(CURSOR_PREF, false);
  expect(getPref(CURSOR_PREF)).toBe(false);
});

test("getPref returns the fallback when the key is unset", () => {
  expect(getPref("ytk:test:absent", true)).toBe(true);
  expect(getPref("ytk:test:absent", false)).toBe(false);
  expect(getPref("ytk:test:absent")).toBe(false);
});

test("getPref honours an explicit false over a true fallback", () => {
  setPref("ytk:test:closed", false);
  expect(getPref("ytk:test:closed", true)).toBe(false);
});

test("setPref round-trips both directions", () => {
  setPref("ytk:test:rt", true);
  expect(getPref("ytk:test:rt")).toBe(true);
  setPref("ytk:test:rt", false);
  expect(getPref("ytk:test:rt")).toBe(false);
});

test("a legacy stored 1 still reads as on", () => {
  localStorage.setItem("ytk:test:legacy", "1");
  expect(getPref("ytk:test:legacy")).toBe(true);
  expect(getPref("ytk:test:legacy", false)).toBe(true);
});
