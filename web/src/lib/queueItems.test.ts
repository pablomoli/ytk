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

/* Reddit is no longer filtered out here — it can no longer enter the queue at
   all, so a leftover row from before the demotion is shown rather than hidden.
   The default selection keeps everything (DEFAULT_HIDDEN is empty). */
test("keeps every source by default", () => {
  const items = filterAndSortQueue([
    { url: "post", source: "reddit", shared_at: "2026-07-10" },
    { url: "video", source: "youtube", shared_at: "2026-07-09" },
  ]);

  expect(items.map((item) => item.url)).toEqual(["post", "video"]);
});

test("an explicit selection still narrows the queue", () => {
  const items = filterAndSortQueue(
    [
      { url: "post", source: "reddit", shared_at: "2026-07-10" },
      { url: "video", source: "youtube", shared_at: "2026-07-09" },
    ],
    new Set(["youtube"]),
  );

  expect(items.map((item) => item.url)).toEqual(["video"]);
});
