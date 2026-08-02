import { afterEach, expect, test } from "vitest";
import { ASK_PROMPT_DEFAULT, ASK_PROMPT_PREF, askPrompt } from "./askPrompt";
import { setStringPref } from "./prefs";

afterEach(() => setStringPref(ASK_PROMPT_PREF, null));

test("default template renders the note path", () => {
  expect(askPrompt("sources/youtube/video.md")).toBe(
    "tell me something about sources/youtube/video.md",
  );
});

test("custom template substitutes every {id}", () => {
  setStringPref(ASK_PROMPT_PREF, "read {id} then quiz me on {id}");
  expect(askPrompt("sources/web/paper.md")).toBe(
    "read sources/web/paper.md then quiz me on sources/web/paper.md",
  );
});

test("template without {id} appends the path", () => {
  setStringPref(ASK_PROMPT_PREF, "summarize this note");
  expect(askPrompt("sources/web/paper.md")).toBe("summarize this note sources/web/paper.md");
});

test("whitespace-only pref falls back to the default", () => {
  setStringPref(ASK_PROMPT_PREF, "   ");
  expect(askPrompt("a.md")).toBe(ASK_PROMPT_DEFAULT.replaceAll("{id}", "a.md"));
});
