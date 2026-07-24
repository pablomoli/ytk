import { expect, test } from "vitest";
import { CURSOR_PREF, getPref, setPref } from "./prefs";

test("prefs round-trip through localStorage, default false", () => {
  expect(getPref(CURSOR_PREF)).toBe(false);
  setPref(CURSOR_PREF, true);
  expect(getPref(CURSOR_PREF)).toBe(true);
  setPref(CURSOR_PREF, false);
  expect(getPref(CURSOR_PREF)).toBe(false);
});
