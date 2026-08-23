import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { page } from "vite-plus/test/browser";
import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";
import type { AtlasData, AtlasFeatures, KnobResult } from "../api/atlas";

const router = vi.hoisted(() => ({
  search: {} as Record<string, unknown>,
  navigate: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({
    options,
    fullPath: "/atlas",
    useSearch: () => router.search,
  }),
  useNavigate: () => router.navigate,
}));

vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const atlas: AtlasData = {
  grid: 2,
  x_edges: [0, 0.5, 1],
  y_edges: [0, 0.5, 1],
  n_map_points: 40,
  n_joined: 38,
  gate: { stable_05: 1, stable_08: 1, strict_05: 1, n: 2 },
  protagonist: {
    latent: 1597,
    cell: [0, 0],
    on_frozen_layout: false,
    cell_method: "10-NN vote estimate",
  },
  cells: [
    {
      cell: [0, 0],
      x0: 0,
      y0: 0,
      x1: 0.5,
      y1: 0.5,
      n_points: 20,
      n_scored: 18,
      ood_frac: 0.1,
      head_mass: 0.4,
      label_latent: 926,
      label: "Mechanistic interpretability research",
      label_excess: 0.01,
      label_outside_null: true,
      top5: [
        {
          latent: 926,
          name: "Mechanistic interpretability research",
          excess: 0.01,
          outside_null: true,
        },
      ],
      seed_cos_top5: [0.9, 0.9],
      stable_05: true,
      stable_08: true,
      theme_label: "frontier AI research",
    },
    {
      cell: [1, 1],
      x0: 0.5,
      y0: 0.5,
      x1: 1,
      y1: 1,
      n_points: 20,
      n_scored: 20,
      ood_frac: 0,
      head_mass: 0.2,
      label_latent: 977,
      label: "EpicMap field service SaaS platform",
      label_excess: 0.02,
      label_outside_null: true,
      top5: [
        {
          latent: 977,
          name: "EpicMap field service SaaS platform",
          excess: 0.02,
          outside_null: true,
        },
      ],
      seed_cos_top5: [0.4, 0.4],
      stable_05: false,
      stable_08: false,
      theme_label: "agentic coding workflows",
    },
  ],
};

const features: AtlasFeatures = {
  checkpoint: "final_d2048_k32_s0.pt",
  naming: "haiku",
  protagonist: 1597,
  cards: {
    "1597": {
      name: "Educational breakdown of language model mechanics",
      confidence: "high",
      freq: 0.018,
      badge: 0.57,
      exemplars: [
        {
          title: "I Built an LLM From Scratch",
          kind: "segment",
          source: "youtube",
          video_id: "abc",
          act: 0.35,
        },
      ],
    },
    "926": {
      name: "Mechanistic interpretability research",
      confidence: "high",
      freq: 0.03,
      badge: 0.85,
      exemplars: [
        {
          title: "The Dark Matter of AI",
          kind: "video",
          source: "youtube",
          video_id: "def",
          act: 0.3,
        },
      ],
    },
    "977": {
      name: "EpicMap field service SaaS platform",
      confidence: "medium",
      freq: 0.021,
      badge: 0.73,
      exemplars: [
        {
          title: "Building a Field Service Map",
          kind: "video",
          source: "youtube",
          video_id: "ghi",
          act: 0.28,
        },
      ],
    },
  },
};

const runKnob = vi.hoisted(() => vi.fn());
const atlasRefetch = vi.hoisted(() => vi.fn());
const featuresRefetch = vi.hoisted(() => vi.fn());

const queryState = {
  atlas: {
    isLoading: false,
    isError: false,
    data: atlas as AtlasData | undefined,
    error: null as unknown,
    refetch: atlasRefetch,
  },
  features: {
    isLoading: false,
    isError: false,
    data: features as AtlasFeatures | undefined,
    error: null as unknown,
    refetch: featuresRefetch,
  },
};

vi.mock("../api/atlas", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/atlas")>()),
  runKnob,
  useAtlas: () => queryState.atlas,
  useAtlasFeatures: () => queryState.features,
}));

import { Route } from "./atlas";

const Page = (Route as unknown as { options: { component: () => React.ReactNode } }).options
  .component;

const knobResult = (title: string, selectedActivation = 0.42): KnobResult => ({
  base: [
    {
      title: `${title} base`,
      kind: "video",
      source: "youtube",
      sim: 0.73,
      share: 0.62,
    },
  ],
  clamped: [
    {
      title: `${title} clamped`,
      kind: "video",
      source: "youtube",
      sim: 0.91,
      share: 0.88,
    },
  ],
  query_latents: [
    { latent: 1597, act: selectedActivation },
    { latent: 8, act: 0.2 },
  ],
  latent_max: 1.5,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  router.search = {};
  router.navigate.mockReset();
  runKnob.mockReset();
  atlasRefetch.mockReset();
  featuresRefetch.mockReset();
  Object.assign(queryState.atlas, {
    isLoading: false,
    isError: false,
    data: atlas,
    error: null,
  });
  Object.assign(queryState.features, {
    isLoading: false,
    isError: false,
    data: features,
    error: null,
  });
});

afterEach(async () => {
  cleanup();
  await page.viewport(1024, 768);
});

describe("/atlas", () => {
  it("opens on the protagonist thread without rewriting its intentional cell-latent pair", () => {
    render(<Page />);

    expect(screen.getByRole("button", { name: /cell 0,0/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByRole("heading", {
        name: /#1597 Educational breakdown of language model mechanics/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/estimated cell/)).toBeInTheDocument();
  });

  it("selects a cell and its label latent atomically through URL state", () => {
    render(<Page />);

    fireEvent.click(screen.getByRole("button", { name: /cell 1,1/i }));

    expect(router.navigate).toHaveBeenCalledWith({
      search: { cell: "1,1", latent: 977 },
    });
  });

  it("uses URL state as the authority when back or forward navigation changes it", () => {
    router.search = { cell: "0,0", latent: 926 };
    const view = render(<Page />);
    expect(
      screen.getByRole("heading", { name: /#926 Mechanistic interpretability research/ }),
    ).toBeInTheDocument();

    router.search = { cell: "1,1", latent: 977 };
    view.rerender(<Page />);

    expect(screen.getByRole("heading", { name: /Cell 1,1/ })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /#977 EpicMap field service SaaS platform/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cell 1,1/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("makes every lattice cell keyboard-selectable", () => {
    render(<Page />);
    const cell = screen.getByRole("button", { name: /cell 1,1/i });

    fireEvent.keyDown(cell, { key: " " });

    expect(router.navigate).toHaveBeenCalledWith({
      search: { cell: "1,1", latent: 977 },
    });
  });

  it("shows the causal payload with truthful base wording and explanatory activations", async () => {
    runKnob.mockResolvedValueOnce(knobResult("current"));
    render(<Page />);

    fireEvent.change(screen.getByRole("textbox", { name: "Query" }), {
      target: { value: "mechanistic interpretability" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run intervention" }));

    expect(await screen.findByText("unclamped roundtrip")).toBeInTheDocument();
    expect(screen.getByText("62% share")).toBeInTheDocument();
    expect(screen.getByText("cosine 0.73")).toBeInTheDocument();
    expect(screen.getByText(/naturally active at 0.42/i)).toBeInTheDocument();
    expect(screen.getByText(/corpus max 1.50/i)).toBeInTheDocument();
    expect(screen.getByText(/#8 at 0.20/i)).toBeInTheDocument();
  });

  it("suppresses an older response when a newer query finishes first", async () => {
    const first = deferred<KnobResult>();
    const second = deferred<KnobResult>();
    runKnob.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    render(<Page />);
    const input = screen.getByRole("textbox", { name: "Query" });

    fireEvent.change(input, { target: { value: "first query" } });
    fireEvent.click(screen.getByRole("button", { name: "Run intervention" }));
    fireEvent.change(input, { target: { value: "second query" } });
    fireEvent.click(screen.getByRole("button", { name: "Run intervention" }));
    second.resolve(knobResult("newer"));
    expect(await screen.findByText("newer clamped")).toBeInTheDocument();

    first.resolve(knobResult("older"));
    await waitFor(() => expect(screen.queryByText("older clamped")).not.toBeInTheDocument());
    expect(screen.getByText("newer clamped")).toBeInTheDocument();
  });

  it("invalidates a successful result as soon as query or clamp intent changes", async () => {
    runKnob.mockResolvedValueOnce(knobResult("stale"));
    render(<Page />);
    const input = screen.getByRole("textbox", { name: "Query" });

    fireEvent.change(input, { target: { value: "first" } });
    fireEvent.click(screen.getByRole("button", { name: "Run intervention" }));
    expect(await screen.findByText("stale clamped")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "edited" } });
    expect(screen.queryByText("stale clamped")).not.toBeInTheDocument();

    runKnob.mockResolvedValueOnce(knobResult("fresh"));
    fireEvent.click(screen.getByRole("button", { name: "Run intervention" }));
    expect(await screen.findByText("fresh clamped")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("slider", { name: "Clamp" }), {
      target: { value: "1.5" },
    });
    expect(screen.queryByText("fresh clamped")).not.toBeInTheDocument();
  });

  it("clears stale output on failure and offers a local retry", async () => {
    runKnob.mockRejectedValueOnce(new Error("Failed to fetch"));
    render(<Page />);

    fireEvent.change(screen.getByRole("textbox", { name: "Query" }), {
      target: { value: "causal test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run intervention" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not reach the local hub/i,
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText(/unclamped roundtrip/i)).not.toBeInTheDocument();
  });

  it("localizes Atlas load failures and exposes recovery", () => {
    Object.assign(queryState.atlas, {
      isLoading: false,
      isError: true,
      data: undefined,
      error: new Error("asset missing"),
    });

    render(<Page />);

    expect(screen.getByRole("alert")).toHaveTextContent(/Atlas could not load/i);
    fireEvent.click(screen.getByRole("button", { name: "Retry Atlas" }));
    expect(atlasRefetch).toHaveBeenCalledOnce();
  });

  it.each([
    { width: 375, height: 812, split: false },
    { width: 768, height: 1024, split: false },
    { width: 1440, height: 900, split: true },
  ])("keeps a usable, overflow-free hierarchy at $width x $height", async (viewport) => {
    await page.viewport(viewport.width, viewport.height);
    render(<Page />);

    const root = screen.getByTestId("atlas-page");
    const lattice = screen.getByRole("group", { name: "Atlas cells" });
    const details = screen.getByRole("region", { name: "Selected Atlas feature" });
    const rootBox = root.getBoundingClientRect();
    const latticeBox = lattice.getBoundingClientRect();
    const detailsBox = details.getBoundingClientRect();

    expect(root.scrollWidth).toBeLessThanOrEqual(root.clientWidth);
    expect(latticeBox.width).toBeGreaterThan(viewport.width * (viewport.split ? 0.5 : 0.72));
    expect(rootBox.right).toBeLessThanOrEqual(viewport.width);
    if (viewport.split) {
      expect(detailsBox.left).toBeGreaterThan(latticeBox.left);
      expect(Math.abs(detailsBox.top - latticeBox.top)).toBeLessThan(8);
    } else {
      expect(detailsBox.top).toBeGreaterThanOrEqual(latticeBox.bottom);
    }
  });
});
