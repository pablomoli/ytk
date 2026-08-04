import { expect, test } from "vitest";
import { isOpenable, provenance } from "./provenance";

test("only http(s) urls are openable", () => {
  expect(isOpenable("https://example.com/a")).toBe(true);
  expect(isOpenable("http://example.com/a")).toBe(true);
  // An iMessage capture's identifier is not a link to anywhere.
  expect(isOpenable("imessage:session:527ad6307d540cd9")).toBe(false);
  expect(isOpenable("javascript:alert(1)")).toBe(false);
  expect(isOpenable("file:///etc/passwd")).toBe(false);
  expect(isOpenable("not a url")).toBe(false);
  expect(isOpenable("")).toBe(false);
});

test("reads the subreddit from a reddit permalink", () => {
  const p = provenance("https://www.reddit.com/r/rust/comments/abc123/some_title/");
  expect(p.domain).toBe("reddit.com");
  expect(p.community).toBe("r/rust");
  expect(p.label).toBe("r/rust");
});

test("reads a reddit user page as u/name", () => {
  expect(provenance("https://reddit.com/user/someone/").community).toBe("u/someone");
});

test("reads owner/repo from a github url", () => {
  expect(provenance("https://github.com/pablomoli/ytk/issues/123").community).toBe("pablomoli/ytk");
});

test("reads an @handle from tiktok and instagram profile urls", () => {
  expect(provenance("https://www.tiktok.com/@someone/video/123").community).toBe("@someone");
  expect(provenance("https://www.instagram.com/@someone/").community).toBe("@someone");
});

/* A watch URL carries a video id, not a channel. Inventing a community here
   would print a wrong name on the card, which is worse than printing none. */
test("does not invent a community for youtube or a bare instagram reel", () => {
  const yt = provenance("https://www.youtube.com/watch?v=dQw4w9WgXcQ");
  expect(yt.community).toBeUndefined();
  expect(yt.label).toBe("");

  const ig = provenance("https://www.instagram.com/reel/DTJgBvqgrfi/");
  expect(ig.community).toBeUndefined();
  expect(ig.label).toBe("");
});

/* First-party platform domains echo nothing when the URL names no community —
   the source badge already says "youtube"; the domain said it again (#163). */
test("platform domains yield no label without a community", () => {
  expect(provenance("https://www.youtube.com/watch?v=abc").label).toBe("");
  expect(provenance("https://www.instagram.com/reel/XYZ/").label).toBe("");
});

test("reddit still yields its community", () => {
  expect(provenance("https://old.reddit.com/r/rust/comments/1/x/").label).toBe("r/rust");
});

test("generic web keeps its domain", () => {
  expect(provenance("https://blog.example.com/post").label).toBe("blog.example.com");
});

test("strips a leading www from the domain", () => {
  expect(provenance("https://news.ycombinator.com/item?id=1").domain).toBe("news.ycombinator.com");
  expect(provenance("https://www.example.com/a").domain).toBe("example.com");
});

/* Queue rows have carried non-URL values before; a card must still render. */
test("returns empty strings rather than throwing on an unparseable url", () => {
  const p = provenance("not a url");
  expect(p.domain).toBe("");
  expect(p.community).toBeUndefined();
  expect(p.label).toBe("");
});
