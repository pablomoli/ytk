import { expect, test } from "vitest";
import {
  DEFAULT_HIDDEN,
  allSources,
  isSourceVisible,
  materializeSources,
  parseSources,
  serializeSources,
  toggleSource,
} from "./sourceFilter";

const AVAILABLE = ["instagram", "youtube", "tiktok", "web"];

test("an absent parameter means 'not chosen yet', not 'nothing selected'", () => {
  expect(parseSources(undefined)).toBeNull();
  expect(parseSources(null)).toBeNull();
  expect(parseSources("")).toBeNull();
});

/* Reddit used to live here. It is now excluded at the source rather than
   hidden at the view, so nothing is hidden and the default shows everything —
   but the mechanism stays for the next source that turns out to be noisy. */
test("nothing is hidden by default", () => {
  expect(DEFAULT_HIDDEN).toEqual([]);
  expect(isSourceVisible(null, "youtube")).toBe(true);
  expect(isSourceVisible(null, "instagram")).toBe(true);
  expect(isSourceVisible(null, "tiktok")).toBe(true);
});

test("a source added to DEFAULT_HIDDEN is dropped from the default", () => {
  DEFAULT_HIDDEN.push("tiktok");
  try {
    expect(isSourceVisible(null, "tiktok")).toBe(false);
    expect(materializeSources(null, AVAILABLE)).toEqual(
      new Set(["instagram", "youtube", "web"]),
    );
  } finally {
    DEFAULT_HIDDEN.length = 0;
  }
});

test("several sources can be selected together", () => {
  const selection = parseSources("youtube,instagram");
  expect(isSourceVisible(selection, "youtube")).toBe(true);
  expect(isSourceVisible(selection, "instagram")).toBe(true);
  expect(isSourceVisible(selection, "web")).toBe(false);
});

test("aliases resolve through their canonical source", () => {
  const selection = parseSources("instagram");
  expect(isSourceVisible(selection, "instagram-reel")).toBe(true);
});

/* An emptied set and an unchosen one look the same if both serialize to
   nothing, and a reload would silently re-show the default sources. */
test("an explicitly emptied selection round-trips as distinct from the default", () => {
  const empty = new Set<string>();
  expect(serializeSources(empty)).toBe("none");
  expect(parseSources("none")).toEqual(empty);
  expect(parseSources("none")).not.toBeNull();
  expect(isSourceVisible(new Set<string>(), "youtube")).toBe(false);
});

test("the default selection serializes to nothing at all", () => {
  expect(serializeSources(null)).toBeUndefined();
});

/* The same selection must always produce the same URL, or an unchanged filter
   pushes a second history entry and back/forward stops matching the view. */
test("serialization is stable regardless of insertion order", () => {
  expect(serializeSources(new Set(["youtube", "instagram"]))).toBe("instagram,youtube");
  expect(serializeSources(new Set(["instagram", "youtube"]))).toBe("instagram,youtube");
});

test("round-trips a selection through the url", () => {
  const selection = new Set(["instagram", "youtube"]);
  expect(parseSources(serializeSources(selection))).toEqual(selection);
});

test("materializing the default yields every available source", () => {
  expect(materializeSources(null, AVAILABLE)).toEqual(new Set(AVAILABLE));
});

test("materializing an explicit selection leaves it alone", () => {
  const selection = new Set(["tiktok"]);
  expect(materializeSources(selection, AVAILABLE)).toEqual(selection);
});

/* Toggling out of the default must first make the default concrete, otherwise
   the first click would drop every other source. */
test("toggling from the default keeps the other visible sources", () => {
  const next = toggleSource(null, "youtube", AVAILABLE);
  expect(next).toEqual(new Set(["instagram", "tiktok", "web"]));
});

test("toggling a selected source removes it", () => {
  expect(toggleSource(new Set(["youtube", "web"]), "web", AVAILABLE)).toEqual(new Set(["youtube"]));
});

test("all sources includes the ones hidden by default", () => {
  expect(allSources(AVAILABLE)).toEqual(new Set(AVAILABLE));
});
