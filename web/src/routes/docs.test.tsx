import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { DocsManifest, DocsSection } from "../api/docs";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({
    options,
    useParams: () => ({ section: "30-coastlines" }),
  }),
  Link: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <a href="#mock" className={className}>
      {children}
    </a>
  ),
}));

// the backdrop needs a real WebGL context; the grid must not depend on it
vi.mock("../lib/docsBackdrop", () => ({
  mountBackdrop: vi.fn(() => ({ dispose: vi.fn() })),
}));

const manifest: DocsManifest = {
  available: true,
  sections: [
    {
      id: "30-coastlines",
      num: 30,
      title: "E30 — Coastlines",
      deck: "The land/sea boundary of the /orb planet.",
      images: [
        "30-coastlines/01-the-planet-unrolled.png",
        "30-coastlines/02-the-named-continents.png",
      ],
      hasVideo: true,
    },
    {
      id: "02-picking",
      num: 2,
      title: "E02 — Picking",
      deck: "Raycasts against instanced spheres.",
      images: [],
      hasVideo: false,
    },
  ],
};

const section: DocsSection = {
  id: "30-coastlines",
  readme:
    "# E30 — Coastlines\n\nThe coast is derived from the record.\n\n" +
    "> **Later:** the cosmetic option was exercised.\n\n" +
    "![unrolled](01-the-planet-unrolled.png)\n",
  files: [
    { name: "01-the-planet-unrolled.png", kind: "image", size: 3 },
    { name: "03-the-planet-turns.mp4", kind: "video", size: 3 },
  ],
};

const manifestState = { isError: false, error: null, data: manifest, refetch: vi.fn() };
vi.mock("../api/docs", async () => ({
  ...(await vi.importActual<typeof import("../api/docs")>("../api/docs")),
  useDocsManifest: () => manifestState,
  useDocsSection: () => ({ isError: false, error: null, data: section, refetch: vi.fn() }),
}));

import { Route as IndexRoute } from "./docs.index";
import { Route as SectionRoute } from "./docs.$section";

type RouteLike = { options: { component: React.ComponentType } };
const renderRoute = (route: unknown) => {
  const Page = (route as RouteLike).options.component;
  return render(<Page />);
};

test("index lists sections newest-first with covers from /docs-media", () => {
  const { container } = renderRoute(IndexRoute);
  const titles = [...container.querySelectorAll("h2")].map((h) => h.textContent);
  expect(titles).toEqual(["E30 — Coastlines", "E02 — Picking"]);
  const img = container.querySelector("img");
  expect(img?.getAttribute("src")).toBe(
    "/docs-media/30-coastlines/01-the-planet-unrolled.png",
  );
  expect(screen.getByText(/e30 · 2 figures · film/)).toBeInTheDocument();
  expect(screen.getByText("no figures")).toBeInTheDocument();
});

test("card arrows page through figures without leaving the card", () => {
  const { container } = renderRoute(IndexRoute);
  // at the first figure only the forward arrow exists
  expect(screen.queryByLabelText("previous figure")).toBeNull();
  fireEvent.click(screen.getByLabelText("next figure"));
  expect(container.querySelector("img")?.getAttribute("src")).toBe(
    "/docs-media/30-coastlines/02-the-named-continents.png",
  );
  expect(screen.getByText("2/2")).toBeInTheDocument();
  // at the last figure the forward arrow is gone; the way back exists
  expect(screen.queryByLabelText("next figure")).toBeNull();
  fireEvent.click(screen.getByLabelText("previous figure"));
  expect(container.querySelector("img")?.getAttribute("src")).toBe(
    "/docs-media/30-coastlines/01-the-planet-unrolled.png",
  );
  // the figure-less card never grows arrows
  expect(screen.getAllByLabelText(/figure/)).toHaveLength(1);
});

test("index explains an unmounted record instead of an empty grid", () => {
  manifestState.data = { available: false, sections: [] };
  renderRoute(IndexRoute);
  expect(screen.getByText("the record is not mounted")).toBeInTheDocument();
  expect(screen.getByText(/YTK_REPO_PATH/)).toBeInTheDocument();
  manifestState.data = manifest;
});

test("section page renders the README with rewritten figure paths and film", () => {
  const { container } = renderRoute(SectionRoute);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("E30 — Coastlines");
  // the Later annotation survives as a blockquote, not flattened prose
  expect(container.querySelector("blockquote")).toHaveTextContent(/Later:/);
  expect(container.querySelector("article img")?.getAttribute("src")).toBe(
    "/docs-media/30-coastlines/01-the-planet-unrolled.png",
  );
  expect(container.querySelector("video")?.getAttribute("src")).toBe(
    "/docs-media/30-coastlines/03-the-planet-turns.mp4",
  );
  // manifest is newest-first: e02 is older, nothing is newer than e30
  expect(screen.getByText(/← E02 — Picking/)).toBeInTheDocument();
  expect(screen.queryByText(/→/)).toBeNull();
});
