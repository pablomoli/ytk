import { expect, test } from "vitest";
import { filterAndSortQueue } from "./queueItems";

test("sorts queue items newest first by shared_at", () => {
  const items = filterAndSortQueue([
    { url: "old", source: "youtube", shared_at: "2026-01-06" },
    { url: "new", source: "youtube", shared_at: "2026-07-10" },
  ]);

  expect(items.map((item) => item.url)).toEqual(["new", "old"]);
});

test("filters source aliases through their canonical source", () => {
  const items = filterAndSortQueue(
    [
      { url: "reel", source: "instagram-reel", shared_at: "2026-07-10" },
      { url: "video", source: "youtube", shared_at: "2026-07-09" },
    ],
    new Set(["instagram"]),
  );

  expect(items.map((item) => item.url)).toEqual(["reel"]);
});

/* The default selection, not an empty one: an unfiltered queue still hides the
   sources excluded by policy (#126). */
test("hides reddit by default and keeps everything else", () => {
  const items = filterAndSortQueue([
    { url: "post", source: "reddit", shared_at: "2026-07-10" },
    { url: "video", source: "youtube", shared_at: "2026-07-09" },
  ]);

  expect(items.map((item) => item.url)).toEqual(["video"]);
});

test("shows reddit once it is explicitly selected", () => {
  const items = filterAndSortQueue(
    [
      { url: "post", source: "reddit", shared_at: "2026-07-10" },
      { url: "video", source: "youtube", shared_at: "2026-07-09" },
    ],
    new Set(["reddit", "youtube"]),
  );

  expect(items.map((item) => item.url)).toEqual(["post", "video"]);
});
