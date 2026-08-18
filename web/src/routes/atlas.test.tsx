import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AtlasData, AtlasFeatures } from "../api/atlas";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
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
        { latent: 926, name: "Mechanistic interpretability research", excess: 0.01, outside_null: true },
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
        { latent: 977, name: "EpicMap field service SaaS platform", excess: 0.02, outside_null: true },
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
        { title: "I Built an LLM From Scratch", kind: "segment", source: "youtube", video_id: "abc", act: 0.35 },
      ],
    },
    "926": {
      name: "Mechanistic interpretability research",
      confidence: "high",
      freq: 0.03,
      badge: 0.85,
      exemplars: [
        { title: "The Dark Matter of AI", kind: "video", source: "youtube", video_id: "def", act: 0.3 },
      ],
    },
  },
};

vi.mock("../api/atlas", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/atlas")>()),
  useAtlas: () => ({
    isLoading: false,
    isError: false,
    data: atlas,
    refetch: () => Promise.resolve(),
  }),
  useAtlasFeatures: () => ({ isLoading: false, isError: false, data: features }),
}));

import { Route } from "./atlas";

const Page = (Route as unknown as { options: { component: () => React.ReactNode } }).options
  .component;

describe("/atlas", () => {
  it("renders the lattice, opens on the protagonist thread, and shows the knob", () => {
    render(<Page />);
    // both cells labeled
    expect(screen.getByText("#926")).toBeInTheDocument();
    expect(screen.getByText("#977")).toBeInTheDocument();
    // opens on the protagonist's estimated cell + latent card
    expect(screen.getByText(/estimated cell/)).toBeInTheDocument();
    expect(
      screen.getByText(/#1597 Educational breakdown of language model mechanics/),
    ).toBeInTheDocument();
    // the knob is on screen with its measured range
    expect(screen.getByText(/section 35's measured range/)).toBeInTheDocument();
    // gate summary in controls
    expect(screen.getByText(/1\/2 labels survive retraining/)).toBeInTheDocument();
  });
});
