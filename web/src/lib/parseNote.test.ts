import { expect, test } from "vitest";
import { parseNote } from "./parseNote";

const YOUTUBE_NOTE = `---
url: https://www.youtube.com/watch?v=kWMGG1zdGkA
title: Loads of New Blender Experiments! (Working on My Short Film)
uploader: Curtis Holt
date: 2026-05-30
tags:
  - blender
  - geometry-nodes
  - python
duration: 00:09:29
image_paths:
  - sources/youtube/thumbnails/kWMGG1zdGkA-thumb.jpg
---

![[kWMGG1zdGkA-thumb.jpg]]

## Thesis
Curtis Holt walks through the latest production assets.

## Commentary
Curtis demos a grab-bag of R&D. **bold** and [links](https://x.com) appear inline.

## Key Concepts
- Geometry Nodes typing demo: a node tree that takes an external text file.
- Equirectangular camera mode: used in Blender to render a shader-built sphere.

## Insights
- The grayscale-colorspace JPEG conversion is the critical gotcha.

## Key Moments
- **00:00** — Introduces the geometry-nodes typing demo file
- **00:45** — Explains you must reassign the text-file path
- **06:30** — Introduces the Blender-to-Space Engine spherical-map tool

## Transcript
<details>
<summary>Raw transcript</summary>

[0:00](https://youtu.be/kWMGG1zdGkA?t=0) I'm currently working on my new animated production.

[1:00](https://youtu.be/kWMGG1zdGkA?t=60) with like different colored elements.

</details>
`;

test("parses a full youtube note: frontmatter, lead, and sections in order with correct kinds", () => {
  const parsed = parseNote(YOUTUBE_NOTE);

  expect(parsed.frontmatter.title).toBe(
    "Loads of New Blender Experiments! (Working on My Short Film)",
  );
  expect(parsed.frontmatter.url).toBe("https://www.youtube.com/watch?v=kWMGG1zdGkA");
  expect(parsed.frontmatter.uploader).toBe("Curtis Holt");
  expect(parsed.frontmatter.date).toBe("2026-05-30");
  expect(parsed.frontmatter.duration).toBe("00:09:29");
  expect(parsed.frontmatter.tags).toEqual(["blender", "geometry-nodes", "python"]);
  expect(parsed.frontmatter.images).toEqual(["sources/youtube/thumbnails/kWMGG1zdGkA-thumb.jpg"]);

  expect(parsed.lead).toBe("");

  const kinds = parsed.sections.map((s) => s.kind);
  expect(kinds).toEqual(["thesis", "commentary", "concepts", "insights", "moments", "transcript"]);

  const headings = parsed.sections.map((s) => s.heading);
  expect(headings).toEqual([
    "Thesis",
    "Commentary",
    "Key Concepts",
    "Insights",
    "Key Moments",
    "Transcript",
  ]);

  const thesis = parsed.sections.find((s) => s.kind === "thesis");
  expect(thesis?.body).toContain("Curtis Holt walks through the latest production assets.");

  const transcript = parsed.sections.find((s) => s.kind === "transcript");
  expect(transcript?.body).toContain("[0:00](https://youtu.be/kWMGG1zdGkA?t=0)");
});

test("parses inline flow tags", () => {
  const raw = `---\ntags: [a, b, c]\n---\n\nsome lead text\n`;
  const parsed = parseNote(raw);
  expect(parsed.frontmatter.tags).toEqual(["a", "b", "c"]);
});

test("bare prose with no frontmatter and no headers goes entirely to lead", () => {
  const raw = "just some plain prose with no structure at all.";
  const parsed = parseNote(raw);
  expect(parsed.frontmatter.tags).toEqual([]);
  expect(parsed.sections).toEqual([]);
  expect(parsed.lead).toBe("just some plain prose with no structure at all.");
});

test("heading kind mapping is case-insensitive", () => {
  const raw = `---\ntags: []\n---\n\n## KEY MOMENTS\n- **00:00** — a moment\n`;
  const parsed = parseNote(raw);
  expect(parsed.sections[0].kind).toBe("moments");
  expect(parsed.sections[0].heading).toBe("KEY MOMENTS");
});

test("obsidian embed in the lead is stripped", () => {
  const raw = `---\ntags: []\n---\n\n![[embed.jpg]]\n\nsome real lead text\n\n## Thesis\nbody\n`;
  const parsed = parseNote(raw);
  expect(parsed.lead).toBe("some real lead text");
  expect(parsed.lead).not.toContain("![[");
});

test("note with no frontmatter block at all still parses sections", () => {
  const raw = "## Thesis\nsomething happened\n";
  const parsed = parseNote(raw);
  expect(parsed.frontmatter.tags).toEqual([]);
  expect(parsed.sections).toEqual([
    { heading: "Thesis", kind: "thesis", body: "something happened" },
  ]);
});

test("image_paths block list parses to full vault-relative paths", () => {
  const raw = `---
tags: []
image_paths:
  - sources/instagram/slides/abc123-img-1.jpg
  - sources/instagram/slides/abc123-img-2.jpg
---

lead text
`;
  const parsed = parseNote(raw);
  expect(parsed.frontmatter.images).toEqual([
    "sources/instagram/slides/abc123-img-1.jpg",
    "sources/instagram/slides/abc123-img-2.jpg",
  ]);
});

test("note without image_paths yields an empty images array", () => {
  const raw = `---\ntags: []\n---\n\nlead text\n`;
  const parsed = parseNote(raw);
  expect(parsed.frontmatter.images).toEqual([]);
});

test("embed inline within a section body is stripped, leaving surrounding text", () => {
  const raw = `---\ntags: []\n---\n\n## Commentary\nsome text ![[embed.jpg]] more text\n`;
  const parsed = parseNote(raw);
  expect(parsed.sections[0].body).not.toContain("![[");
  expect(parsed.sections[0].body).toContain("some text");
  expect(parsed.sections[0].body).toContain("more text");
});

test("unrecognized heading maps to generic", () => {
  const raw = `---\ntags: []\n---\n\n## Random Notes\nsome content\n`;
  const parsed = parseNote(raw);
  expect(parsed.sections[0].kind).toBe("generic");
});

test("a Description heading maps to the description kind", () => {
  const raw = `---\ntags: []\n---\n\n## Description\n<details>\n<summary>Video description</summary>\n\nsome text\n</details>\n`;
  const parsed = parseNote(raw);
  expect(parsed.sections[0].kind).toBe("description");
});
