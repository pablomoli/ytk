import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
}));

const api = vi.hoisted(() => ({
  status: { data: { state: "idle", proposals: [] } as import("../api/tagMerge").TagMergeStatus },
  propose: { isPending: false, mutate: vi.fn() },
  apply: { isPending: false, mutate: vi.fn() },
}));

vi.mock("../api/tagMerge", () => ({
  useTagMergeStatus: () => api.status,
  useProposeTagMerges: () => api.propose,
  useApplyTagMerges: () => api.apply,
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../lib/useHoverDecode", () => ({
  useHoverDecode: () => ({ onMouseEnter: () => {} }),
}));

import { Route } from "./tags";
import { TooltipProvider } from "../components/ui/tooltip";

const proposals = [
  {
    canonical: "user-interface",
    variants: ["ui", "ux"],
    counts: { "user-interface": 12, ui: 7, ux: 4 },
  },
];

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
  api.status.data = { state: "idle", proposals: [] };
  api.propose.isPending = false;
  api.apply.isPending = false;
  api.propose.mutate.mockReset();
  api.apply.mutate.mockReset();
});

afterEach(() => vi.clearAllMocks());

test("classifies the route as periodic tag cleanup with an idle state", () => {
  renderPage();
  expect(screen.getByRole("heading", { level: 1, name: "Tag cleanup" })).toBeInTheDocument();
  expect(screen.getByText(/vocabulary maintenance/i)).toBeInTheDocument();
  expect(screen.getByText(/No cleanup is running/i)).toBeInTheDocument();
});

test("announces model-backed running and error states without an ETA", () => {
  api.status.data = { state: "running", proposals: [] };
  const view = renderPage();
  expect(screen.getByRole("status")).toHaveTextContent(/finding duplicate tag vocabulary/i);
  expect(screen.queryByText(/minute|eta|cost/i)).toBeNull();

  api.status.data = { state: "error", detail: "model unavailable", proposals: [] };
  view.rerender(
    <TooltipProvider delayDuration={0}>
      <Page />
    </TooltipProvider>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("model unavailable");
});

test("proposal controls expose canonical, exclusion, merge, and skip state", async () => {
  api.status.data = { state: "done", proposals };
  renderPage();

  const canonical = await screen.findByRole("button", { name: /user-interface.*canonical/i });
  expect(canonical).toHaveAttribute("aria-pressed", "true");
  const exclusion = screen.getByRole("button", { name: "Exclude ui from this merge" });
  expect(exclusion).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(exclusion);
  expect(screen.getByRole("button", { name: "Include ui in this merge" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  expect(screen.getByRole("button", { name: "Merge this group" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  fireEvent.click(screen.getByRole("button", { name: "Skip this group" }));
  expect(screen.getByRole("button", { name: "Skip this group" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("requires confirmation before applying the selected alias mapping", async () => {
  api.status.data = { state: "done", proposals };
  renderPage();
  await screen.findByRole("button", { name: /user-interface.*canonical/i });

  fireEvent.click(screen.getByRole("button", { name: "Apply selected merges" }));
  expect(api.apply.mutate).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toHaveTextContent(/apply 2 tag aliases/i);

  fireEvent.click(screen.getByRole("button", { name: "Apply merges" }));
  await waitFor(() => expect(api.apply.mutate).toHaveBeenCalledTimes(1));
  expect(api.apply.mutate.mock.calls[0][0]).toEqual({ ui: "user-interface", ux: "user-interface" });
});
