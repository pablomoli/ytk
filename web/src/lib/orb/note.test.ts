import { expect, test } from "vitest";
import type { OrbPoint } from "../../api/orb";
import { orbPointToFreshNote } from "./note";

test("maps an orb point onto the NoteViewer contract", () => {
  const p: OrbPoint = {
    p: "second-brain/sources/youtube/some-video.md",
    t: "Some Video", c: "youtube", u: "https://youtu.be/x", d: "2026-01-02",
    th: 3, thumb: "sources/youtube/thumbnails/x-thumb.jpg",
  };
  const note = orbPointToFreshNote(p);
  expect(note.path).toBe(p.p);
  expect(note.stem).toBe("some-video");
  expect(note.title).toBe("Some Video");
  expect(note.source).toBe("youtube");
  expect(note.url).toBe("https://youtu.be/x");
  expect(note.thumbnail).toBe(p.thumb);
  expect(note.tags).toEqual([]);
  expect(note.date).toBe("2026-01-02");
  expect(note.added).toBe("2026-01-02");
  expect(note.has_take).toBe(false);
});

test("nulls stay null and stem survives odd paths", () => {
  const note = orbPointToFreshNote({ p: "a.md", t: "a", c: "web", th: -1 });
  expect(note.stem).toBe("a");
  expect(note.url).toBeNull();
  expect(note.date).toBeNull();
  expect(note.added).toBe("");
  expect(note.has_take).toBe(false);
});
