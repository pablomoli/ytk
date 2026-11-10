import { describe, expect, it } from "vitest";
import { validateOrbSearch } from "./orbSearch";

describe("orb search param", () => {
  it("accepts a non-negative integer theme", () => {
    expect(validateOrbSearch({ theme: 3 })).toEqual({ theme: 3 });
  });
  it("drops junk", () => {
    expect(validateOrbSearch({ theme: "3" })).toEqual({});
    expect(validateOrbSearch({ theme: -1 })).toEqual({});
    expect(validateOrbSearch({})).toEqual({});
  });
});
