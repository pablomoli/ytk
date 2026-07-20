import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({
    options,
    fullPath: "/inbox",
    useSearch: () => ({}),
  }),
  useNavigate: () => vi.fn(),
}));
vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQuery: () => ({ data: ["design"] }),
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../components/MasonryGrid", () => ({
  MasonryGrid: ({ children }: { children: React.ReactNode }) => (
    <main className="masonry">{children}</main>
  ),
}));
vi.mock("../lib/useInfiniteWindow", () => ({
  useInfiniteWindow: (items: unknown[]) => ({ visible: items, sentinelRef: vi.fn() }),
}));

const startRank = vi.fn();
const queue = [
  { url: "new", source: "tiktok", text: "Newest ordinary item", shared_at: "2026-07-20" },
  { url: "match", source: "tiktok", text: "Strong profile match", shared_at: "2026-07-01" },
];

vi.mock("../api/queue", () => ({
  useQueue: () => ({ isLoading: false, isError: false, data: queue }),
}));
vi.mock("../api/job", () => ({
  useJobStatus: () => ({
    data: { running: false, total: 0, done: 0, current: null, queued: [], failures: [] },
  }),
}));
vi.mock("../api/mutations", () => ({
  useAddUrls: () => ({ mutate: vi.fn(), isPending: false }),
  useRefreshSources: () => ({ mutate: vi.fn(), isPending: false }),
  useIngest: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../api/profileRank", () => ({
  useProfileRank: () => ({
    data: {
      state: "done",
      detail: "",
      generated_at: "2026-07-20T04:00:00Z",
      candidates: 1800,
      picks: [
        {
          url: "match",
          title: "Strong profile match",
          source: "tiktok",
          theme: "Creative coding",
          score: 0.731,
        },
      ],
    },
  }),
  useStartProfileRank: () => ({ mutate: startRank, isPending: false }),
}));

import { Route } from "./inbox";

function renderPage() {
  const Page = (Route as unknown as { options: { component: React.ComponentType } }).options
    .component;
  return render(<Page />);
}

test("promotes and highlights cached profile picks before ordinary inbox items", () => {
  const { container } = renderPage();
  const cards = [...container.querySelectorAll(".masonry .card")];
  expect(cards[0].textContent).toContain("Strong profile match");
  expect(cards[0]).toHaveClass("profile-match");
  expect(screen.getByText("match 0.73")).toBeInTheDocument();
  expect(screen.getByText("1 highlighted · 1800 text items scored")).toBeInTheDocument();
});

test("offers an explicit re-rank action for cached results", () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "re-rank by profile" }));
  expect(startRank).toHaveBeenCalledTimes(1);
});
