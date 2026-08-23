import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { page } from "vitest/browser";
import { beforeEach, expect, test, vi } from "vitest";
import type { MapData, MapPoint } from "../api/map";
import { TooltipProvider } from "../components/ui/tooltip";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
}));

const mocks = vi.hoisted(() => ({
  resetCamera: vi.fn(),
  zoomBy: vi.fn(),
  setRoadPick: vi.fn(),
  pathArgs: [] as Array<[string | undefined, string | undefined]>,
}));

const point = (title: string, url: string, x: number): MapPoint => ({
  x,
  y: x,
  z3: [x, x, 0],
  t: title,
  c: "youtube",
  u: url,
  g: 0,
  r: 0,
  dom: 0,
});

const data = {
  v: 2,
  points: [point("Alpha", "u:alpha", 0), point("Beta", "u:beta", 0.5)],
  all: {
    domains: [{ label: "Knowledge", n: 2, x: 0, y: 0 }],
    groups: [{ label: "Systems", n: 2, domain: 0 }],
    params: { trustworthiness_3d: 0.91, silhouette: 0.42 },
    terrain: { h: 1, levels: [], contours: [], ridges: [] },
    web: { h: 1, filaments: [] },
    fog: { h: 1, splats: [] },
  },
  content: {
    groups: [],
    params: { trustworthiness_3d: 0.88, silhouette: 0.33 },
    terrain: { h: 1, levels: [], contours: [], ridges: [] },
    web: { h: 1, filaments: [] },
    fog: { h: 1, splats: [] },
  },
} satisfies MapData;

const renderer = {
  setView: vi.fn(),
  setDimension: vi.fn(),
  setFilters: vi.fn(),
  setClock: vi.fn(),
  setFocus: vi.fn(),
  setHover: vi.fn(),
  setHiddenDomains: vi.fn(),
  setLegendOpen: vi.fn(),
  setTerrain: vi.fn(),
  setWeb: vi.fn(),
  setFog: vi.fn(),
  setFogLevel: vi.fn(),
  setFogShell: vi.fn(),
  setRoadPick: mocks.setRoadPick,
  setRoute: vi.fn(),
  setRouteActive: vi.fn(),
  flyTo: vi.fn(),
  resetCamera: mocks.resetCamera,
  zoomBy: mocks.zoomBy,
  destroy: vi.fn(),
};

vi.mock("../api/map", async () => {
  const actual = await vi.importActual<typeof import("../api/map")>("../api/map");
  return {
    ...actual,
    useMap: () => ({ isLoading: false, isError: false, data }),
  };
});
vi.mock("../api/path", () => ({
  usePath: (a?: string, b?: string) => {
    mocks.pathArgs.push([a, b]);
    return { data: undefined, isLoading: false, error: null };
  },
}));
vi.mock("../lib/mapRenderer", () => ({
  mountMapRenderer: () => renderer,
  mapDomainColor: () => "rgb(1, 2, 3)",
  mapSubColor: () => "rgb(4, 5, 6)",
  mapGroupColor: () => "rgb(7, 8, 9)",
}));

import { Route } from "./map";

const Page = (Route as unknown as { options: { component: React.ComponentType } }).options
  .component;

function renderPage() {
  return render(
    <TooltipProvider delayDuration={0}>
      <Page />
    </TooltipProvider>,
  );
}

beforeEach(() => {
  history.replaceState(null, "", "/map");
  mocks.pathArgs.length = 0;
  vi.clearAllMocks();
});

test("groups view, filters, projection, layers, tool, and camera in keyboard order", () => {
  renderPage();
  const controls = screen.getByRole("region", { name: "Map controls" });
  // Radix single toggle items are native <button role="radio">; DOM order of
  // every button is the tab order across radios and plain buttons alike.
  const names = Array.from(controls.querySelectorAll("button")).map(
    (button) => button.getAttribute("aria-label") || button.textContent?.trim(),
  );
  expect(names.slice(0, 9)).toEqual([
    "Everything",
    "Content",
    "Filters",
    "2D",
    "3D",
    "Layers",
    "Road",
    "Home camera",
    "Zoom out",
  ]);
  expect(within(controls).getByRole("toolbar", { name: "Map camera" })).toBeInTheDocument();
});

test("2D clears volume layers through the shared state rules", () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "Layers" }));
  fireEvent.click(screen.getByRole("button", { name: "Web" }));
  expect(screen.getByRole("button", { name: "Web" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("radio", { name: "3D" })).toHaveAttribute("data-state", "on");

  fireEvent.click(screen.getByRole("radio", { name: "2D" }));
  expect(screen.getByRole("button", { name: "Web" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("button", { name: "Fog" })).toHaveAttribute("aria-pressed", "false");
});

test("Home changes camera only while Reset clears the whole map state", () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "Filters" }));
  fireEvent.click(screen.getByRole("button", { name: "Signal" }));
  fireEvent.click(screen.getByRole("button", { name: "Home camera" }));
  expect(mocks.resetCamera).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Signal" })).toHaveAttribute("aria-pressed", "true");

  fireEvent.click(screen.getByRole("button", { name: "Reset map" }));
  expect(mocks.resetCamera).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Signal" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("radio", { name: "Everything" })).toHaveAttribute("data-state", "on");
});

test("camera zoom commands call the renderer's center-anchored seam", () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
  fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
  expect(mocks.zoomBy.mock.calls.map((call) => call[0])).toEqual([0.8, 1.25]);
});

test("Road offers bounded keyboard endpoint selectors through the same path state", () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "Road" }));
  fireEvent.change(screen.getByLabelText("Road start"), { target: { value: "u:alpha" } });
  fireEvent.change(screen.getByLabelText("Road destination"), { target: { value: "u:beta" } });
  expect(mocks.pathArgs).toContainEqual(["u:alpha", "u:beta"]);
});

test("resting chrome has one note count and hides diagnostics and gesture help", () => {
  renderPage();
  expect(screen.getAllByText("2 notes")).toHaveLength(1);
  expect(screen.queryByText(/trust 0.91/i)).toBeNull();
  expect(screen.queryByText(/drag orbit/i)).toBeNull();

  fireEvent.click(screen.getByText("Diagnostics"));
  expect(screen.getByText(/trust 0.91/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Map help" }));
  expect(screen.getByText(/drag to orbit/i)).toBeInTheDocument();
});

test.each([
  [375, 812],
  [768, 1024],
  [1440, 900],
])("controls do not overflow a %ix%i viewport", async (width, height) => {
  await page.viewport(width, height);
  await act(async () => renderPage());
  const controls = screen.getByRole("region", { name: "Map controls" });
  expect(controls.getBoundingClientRect().right).toBeLessThanOrEqual(width);
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width);
});
