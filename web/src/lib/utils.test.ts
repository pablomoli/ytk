import { expect, test } from "vitest";
import { cn } from "./utils";

test("cn resolves conflicting utilities in favor of the caller", () => {
  expect(cn("p-2 text-mute", "p-4")).toBe("text-mute p-4");
});

test("cn drops falsy conditionals", () => {
  expect(cn("card", false, undefined, null, "on")).toBe("card on");
});
