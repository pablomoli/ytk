import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { SettingsConfig } from "../../api/settings";
import { cloneSettings } from "../../lib/settingsDraft";
import {
  CadenceSection,
  EnvironmentSection,
  HubSection,
  IngestFiltersSection,
  InterestSection,
  MapColorSection,
  MiscSection,
  ToneSection,
} from "./SettingsSections";
import type { UpdateSettings } from "./SettingsSections";

const config = {
  filters: {
    min_duration: 60,
    max_duration: 900,
    require_captions: true,
    interest_tags: ["design"],
  },
  hub: {
    host: "127.0.0.1",
    port: 6969,
    favicon: "Y",
    cadence_minutes: { youtube: 15 },
    imessage_gap_minutes: 20,
    tags: ["design"],
    pinterest_feeds: [],
    enrich_tone: "direct",
  },
  whisper_model: "base",
  memo_notify: ["tmux"],
  github_repos: ["pablomoli/ytk"],
  interest: {
    cluster_min: 3,
    cluster_max: 24,
    content_sources: ["youtube"],
    alpha: 7,
    explicit_min: 5,
  },
  map: {
    color_rules: [
      { query: "work", color: "#e2b04a" },
      { query: "play", color: "#6f8fc9" },
    ],
    presets: {},
  },
} satisfies SettingsConfig;

function captureUpdate() {
  let current = cloneSettings(config);
  const update: UpdateSettings = (change) => {
    const next = cloneSettings(current);
    change(next);
    current = next;
  };
  return { update, current: () => current };
}

test("hub section emits scalar and list updates", () => {
  const state = captureUpdate();
  render(<HubSection draft={config} update={state.update} fieldError={() => undefined} />);

  fireEvent.change(screen.getByLabelText(/^host/), { target: { value: "0.0.0.0" } });
  fireEvent.click(screen.getByRole("button", { name: "Remove design" }));

  expect(state.current().hub.host).toBe("0.0.0.0");
  expect(state.current().hub.tags).toEqual([]);
});

test("cadence and interest sections emit typed updates and external actions", () => {
  const state = captureUpdate();
  const onRefresh = vi.fn();
  const { rerender } = render(
    <CadenceSection
      draft={config}
      update={state.update}
      onRefresh={onRefresh}
      refreshPending={false}
    />,
  );
  fireEvent.change(screen.getByLabelText("youtube"), { target: { value: "30" } });
  fireEvent.click(screen.getByRole("button", { name: "Pull all sources now" }));
  expect(state.current().hub.cadence_minutes.youtube).toBe(30);
  expect(onRefresh).toHaveBeenCalledTimes(1);

  rerender(<InterestSection draft={config} update={state.update} />);
  fireEvent.click(screen.getByLabelText("instagram"));
  expect(state.current().interest.content_sources).toEqual(["youtube", "instagram"]);
});

test("map section emits rule ordering updates", () => {
  const state = captureUpdate();
  render(<MapColorSection draft={config} update={state.update} fieldError={() => undefined} />);
  const section = screen.getByText("Map color rules").parentElement!;

  fireEvent.click(within(section).getAllByRole("button", { name: "↓" })[0]);

  expect(state.current().map.color_rules.map((rule) => rule.query)).toEqual(["play", "work"]);
});

test("filter and misc sections emit nullable, checkbox, and scalar updates", () => {
  const state = captureUpdate();
  const { rerender } = render(<IngestFiltersSection draft={config} update={state.update} />);
  fireEvent.change(screen.getByLabelText("max duration"), { target: { value: "" } });
  fireEvent.click(screen.getByLabelText("require captions"));
  expect(state.current().filters.max_duration).toBeNull();
  expect(state.current().filters.require_captions).toBe(false);

  rerender(<MiscSection draft={config} update={state.update} />);
  fireEvent.change(screen.getByLabelText("whisper model"), { target: { value: "small" } });
  expect(state.current().whisper_model).toBe("small");
});

test("tone and environment sections remain controlled by their callers", () => {
  const onChange = vi.fn();
  const onPreview = vi.fn();
  const { rerender } = render(
    <ToneSection tone="direct" onChange={onChange} onPreview={onPreview} previewPending={false} />,
  );
  fireEvent.change(screen.getByLabelText("tone"), { target: { value: "skeptical" } });
  fireEvent.click(screen.getByRole("button", { name: "Preview on 5 notes" }));
  expect(onChange).toHaveBeenCalledWith("skeptical");
  expect(onPreview).toHaveBeenCalledWith("direct");

  rerender(<EnvironmentSection environment={{ chroma_mode: "embedded" }} />);
  expect(screen.getByText("embedded")).toBeInTheDocument();
});
