import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { SettingsConfig, SettingsResponse } from "../api/settings";
import { queryClient } from "../api/client";
import { SettingsPage } from "./settings";

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

const response = {
  config,
  meta: {
    restart_required_fields: ["hub.host", "hub.port"],
    last_pulls: {},
    environment: { chroma_mode: "embedded" },
  },
} satisfies SettingsResponse;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installApi(saveResponse: Response = json({ saved: true, restart_required: false })) {
  const saved: SettingsConfig[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.pathname
            : new URL(input.url).pathname;
      if (path === "/api/settings" && (!init?.method || init.method === "GET"))
        return json({ ...response, config: saved.at(-1) ?? response.config });
      if (path === "/api/settings" && init?.method === "PUT") {
        if (typeof init.body !== "string") throw new Error("settings body must be JSON");
        saved.push(JSON.parse(init.body) as SettingsConfig);
        return saveResponse;
      }
      if (path === "/api/garden-buckets")
        return json({ text: "buckets: []\n", path: "~/.ytk/garden_buckets.yaml" });
      throw new Error(`unexpected request: ${path}`);
    }),
  );
  return saved;
}

function renderPage() {
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => queryClient.clear());
afterEach(() => {
  queryClient.clear();
  vi.unstubAllGlobals();
});

test("loads one draft and saves scalar, nullable, list, checkbox, and rule-order edits", async () => {
  const saved = installApi();
  renderPage();

  expect(screen.getByText("loading settings...")).toBeInTheDocument();
  fireEvent.change(await screen.findByLabelText(/^host/), { target: { value: "0.0.0.0" } });
  await screen.findByText(/topic buckets for the garden/);
  fireEvent.change(screen.getByLabelText("max duration"), { target: { value: "" } });
  fireEvent.click(screen.getByLabelText("require captions"));

  const hubSection = screen.getByText("Hub").parentElement!;
  fireEvent.click(within(hubSection).getByRole("button", { name: "Remove design" }));

  const rules = screen.getByText("Map color rules").parentElement!;
  fireEvent.click(within(rules).getAllByRole("button", { name: "↓" })[0]);
  fireEvent.click(screen.getByRole("button", { name: "Save", hidden: true }));

  await waitFor(() => expect(saved).toHaveLength(1));
  expect(saved[0].hub.host).toBe("0.0.0.0");
  expect(saved[0].filters.max_duration).toBeNull();
  expect(saved[0].filters.require_captions).toBe(false);
  expect(saved[0].hub.tags).toEqual([]);
  expect(saved[0].map.color_rules.map((rule) => rule.query)).toEqual(["play", "work"]);
  await waitFor(() => expect(screen.getByLabelText(/^host/)).toHaveValue("0.0.0.0"));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Save", hidden: true })).toBeNull(),
  );
});

test("maps server validation errors onto the owning field", async () => {
  installApi(
    json(
      {
        detail: [{ loc: "hub.port", msg: "must be positive" }],
      },
      422,
    ),
  );
  renderPage();

  fireEvent.change(await screen.findByLabelText(/^port/), { target: { value: "-1" } });
  fireEvent.click(screen.getByRole("button", { name: "Save", hidden: true }));

  expect(await screen.findByText("must be positive")).toBeInTheDocument();
  expect(screen.getByLabelText(/^port/)).toHaveClass("err");
});

test("revert restores the last saved draft", async () => {
  installApi();
  renderPage();

  const host = await screen.findByLabelText(/^host/);
  fireEvent.change(host, { target: { value: "0.0.0.0" } });
  fireEvent.click(screen.getByRole("button", { name: "Revert", hidden: true }));

  expect(screen.getByLabelText(/^host/)).toHaveValue("127.0.0.1");
  expect(screen.queryByRole("button", { name: "Save", hidden: true })).toBeNull();
});
