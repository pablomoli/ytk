import { expect, test } from "vitest";
import { cloneSettings, isDirty, nearestValidationPath, validationByPath } from "./settingsDraft";
import type { SettingsConfig } from "../api/settings";

const config = {
  filters: { min_duration: 60, max_duration: null, require_captions: true, interest_tags: [] },
  hub: {
    host: "127.0.0.1",
    port: 6969,
    favicon: "✦",
    cadence_minutes: {},
    imessage_gap_minutes: 20,
    tags: ["design"],
    pinterest_feeds: [],
    enrich_tone: "",
  },
  whisper_model: "base",
  memo_notify: [],
  github_repos: [],
  interest: { cluster_min: 3, cluster_max: 24, content_sources: [], alpha: 7, explicit_min: 5 },
  map: { color_rules: [{ query: "work", color: "#e2b04a" }], presets: {} },
} satisfies SettingsConfig;

test("clones drafts without sharing nested lists", () => {
  const draft = cloneSettings(config);
  draft.map.color_rules[0].query = "changed";
  expect(config.map.color_rules[0].query).toBe("work");
  expect(isDirty(draft, config)).toBe(true);
});

test("maps dot-joined server validation paths to owning controls", () => {
  const errors = validationByPath([{ loc: "hub.port", msg: "must be positive" }]);
  expect(nearestValidationPath("hub.port", errors)).toBe("hub.port");
  expect(nearestValidationPath("hub", errors)).toBe("hub.port");
});
