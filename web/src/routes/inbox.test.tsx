import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

let routeSearch: { source?: string } = {};

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({
    options,
    fullPath: "/inbox",
    useSearch: () => routeSearch,
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
  { url: "other-match", source: "reddit", text: "Other profile match", shared_at: "2026-06-01" },
];

const completedRank = {
  state: "done" as const,
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
    {
      url: "other-match",
      title: "Other profile match",
      source: "reddit",
      theme: "Design",
      score: 0.68,
    },
  ],
};
let rankQuery: { data?: typeof completedRank; isError: boolean } = {
  data: completedRank,
  isError: false,
};

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
  useProfileRank: () => rankQuery,
  useStartProfileRank: () => ({ mutate: startRank, isPending: false }),
}));

import { Route } from "./inbox";

function renderPage() {
  const Page = (Route as unknown as { options: { component: React.ComponentType } }).options
    .component;
  return render(<Page />);
}

beforeEach(() => {
  routeSearch = {};
  rankQuery = { data: completedRank, isError: false };
  startRank.mockClear();
});

test("promotes and highlights cached profile picks before ordinary inbox items", () => {
  const { container } = renderPage();
  const cards = [...container.querySelectorAll(".masonry .card")];
  expect(cards[0].textContent).toContain("Strong profile match");
  expect(cards[0]).toHaveClass("profile-match");
  // The card carries a quiet theme tag, not a numeric score pill.
  expect(cards[0].querySelector(".profile-theme-tag")).toHaveTextContent("Creative coding");
  expect(screen.queryByText(/match 0\.\d+/)).not.toBeInTheDocument();
  expect(screen.getByText(/2 highlighted · 1800 text items scored · updated 2026-07-20/)).toBeInTheDocument();
});

test("offers an explicit re-rank action for cached results", () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "re-rank by profile" }));
  expect(startRank).toHaveBeenCalledTimes(1);
});

test("highlighted count follows the active source filter", () => {
  routeSearch = { source: "tiktok" };
  renderPage();
  expect(screen.getByText(/1 highlighted · 1800 text items scored/)).toBeInTheDocument();
});

test("shows transport errors from the profile-rank status endpoint", () => {
  rankQuery = { isError: true };
  renderPage();
  expect(screen.getByText("rank status unavailable")).toBeInTheDocument();
});

test("reroll pages through stratified batches, moves the highlight, and wraps", () => {
  const filler = (prefix: string, n: number) =>
    Array.from({ length: n }, (_, i) => ({
      url: `${prefix}${i}`,
      title: `${prefix}${i}`,
      source: "web",
      theme: "Filler",
      score: 0.5,
    }));
  // 45 picks => two batches of 30. "match" leads batch 1; "other-match" sits at
  // index 30, so it only appears once the user rerolls to batch 2.
  rankQuery = {
    data: {
      ...completedRank,
      picks: [
        { url: "match", title: "Strong profile match", source: "tiktok", theme: "Creative coding", score: 0.9 },
        ...filler("a", 29),
        { url: "other-match", title: "Other profile match", source: "reddit", theme: "Design", score: 0.6 },
        ...filler("b", 14),
      ],
    },
    isError: false,
  };
  const { container } = renderPage();
  const findCard = (text: string) =>
    [...container.querySelectorAll(".masonry .card")].find((c) => c.textContent?.includes(text));

  expect(screen.getByText("batch 1/2")).toBeInTheDocument();
  expect(findCard("Strong profile match")).toHaveClass("profile-match");
  expect(findCard("Other profile match")).not.toHaveClass("profile-match");

  fireEvent.click(screen.getByRole("button", { name: "reroll" }));
  expect(screen.getByText("batch 2/2")).toBeInTheDocument();
  expect(findCard("Other profile match")).toHaveClass("profile-match");
  expect(findCard("Strong profile match")).not.toHaveClass("profile-match");

  // reset returns to the first batch
  fireEvent.click(screen.getByRole("button", { name: "reset" }));
  expect(screen.getByText("batch 1/2")).toBeInTheDocument();

  // reroll wraps from the last batch back to the first
  fireEvent.click(screen.getByRole("button", { name: "reroll" }));
  fireEvent.click(screen.getByRole("button", { name: "reroll" }));
  expect(screen.getByText("batch 1/2")).toBeInTheDocument();
});
