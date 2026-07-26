import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

let routeSearch: { sources?: string } = {};

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
  { url: "other-match", source: "pinterest", text: "Other profile match", shared_at: "2026-06-01" },
  // Hidden by default (#126), so it is only in the grid when asked for.
  { url: "red", source: "reddit", text: "Reddit item", shared_at: "2026-05-01" },
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

const SHOW_MATCHES_KEY = "ytk:inbox:show-profile-matches";
const enableMatches = () => localStorage.setItem(SHOW_MATCHES_KEY, "1");

beforeEach(() => {
  routeSearch = {};
  rankQuery = { data: completedRank, isError: false };
  startRank.mockClear();
  localStorage.clear();
});

test("keeps a cached ranking quiet until the toggle is on", () => {
  const { container } = renderPage();
  const cards = [...container.querySelectorAll(".masonry .card")];
  // Default off: the newest ordinary item leads, no card is promoted or badged.
  expect(cards[0].textContent).toContain("Newest ordinary item");
  expect(container.querySelector(".card.profile-match")).toBeNull();
  expect(container.querySelector(".profile-theme-tag")).toBeNull();
  expect(screen.queryByRole("button", { name: "reroll" })).not.toBeInTheDocument();
  // The toggle itself is offered because a ranking exists.
  expect(screen.getByLabelText("show matches in grid")).not.toBeChecked();
});

test("the toggle reveals matches and persists the choice", () => {
  const { container } = renderPage();
  fireEvent.click(screen.getByLabelText("show matches in grid"));
  const cards = [...container.querySelectorAll(".masonry .card")];
  expect(cards[0].textContent).toContain("Strong profile match");
  expect(cards[0]).toHaveClass("profile-match");
  expect(localStorage.getItem(SHOW_MATCHES_KEY)).toBe("1");
});

test("ranking by profile auto-enables the toggle so the result is visible", () => {
  const { container } = renderPage();
  expect(container.querySelector(".card.profile-match")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "re-rank by profile" }));
  expect(startRank).toHaveBeenCalledTimes(1);
  expect(container.querySelector(".card.profile-match")).not.toBeNull();
});

test("promotes and highlights cached profile picks before ordinary inbox items", () => {
  enableMatches();
  const { container } = renderPage();
  const cards = [...container.querySelectorAll(".masonry .card")];
  expect(cards[0].textContent).toContain("Strong profile match");
  expect(cards[0]).toHaveClass("profile-match");
  // The card carries a quiet theme tag, not a numeric score pill.
  expect(cards[0].querySelector(".profile-theme-tag")).toHaveTextContent("Creative coding");
  expect(screen.queryByText(/match 0\.\d+/)).not.toBeInTheDocument();
  expect(
    screen.getByText(/2 highlighted · 1800 text items scored · updated 2026-07-20/),
  ).toBeInTheDocument();
});

test("offers an explicit re-rank action for cached results", () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "re-rank by profile" }));
  expect(startRank).toHaveBeenCalledTimes(1);
});

test("highlighted count follows the active source filter", () => {
  enableMatches();
  routeSearch = { sources: "tiktok" };
  renderPage();
  expect(screen.getByText(/1 highlighted · 1800 text items scored/)).toBeInTheDocument();
});

/* #126: reddit is excluded until asked for, and asking is a URL away. */
test("hides reddit until it is explicitly selected", () => {
  const { container } = renderPage();
  const text = () => [...container.querySelectorAll(".masonry .card")].map((c) => c.textContent);
  expect(text().join(" ")).not.toContain("Reddit item");

  routeSearch = { sources: "reddit" };
  const second = renderPage();
  expect(
    [...second.container.querySelectorAll(".masonry .card")].map((c) => c.textContent).join(" "),
  ).toContain("Reddit item");
});

test("several sources can be filtered at once", () => {
  routeSearch = { sources: "tiktok,reddit" };
  const { container } = renderPage();
  const text = [...container.querySelectorAll(".masonry .card")]
    .map((c) => c.textContent)
    .join(" ");
  expect(text).toContain("Reddit item");
  expect(text).toContain("Newest ordinary item");
  expect(text).not.toContain("Other profile match");
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
  enableMatches();
  rankQuery = {
    data: {
      ...completedRank,
      picks: [
        {
          url: "match",
          title: "Strong profile match",
          source: "tiktok",
          theme: "Creative coding",
          score: 0.9,
        },
        ...filler("a", 29),
        {
          url: "other-match",
          title: "Other profile match",
          source: "pinterest",
          theme: "Design",
          score: 0.6,
        },
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

test("the rail splits into five independently collapsible widgets", async () => {
  const { container } = renderPage();
  await screen.findAllByRole("group");
  /* Scoped to the rail's own <details> rather than every role="group" on the
     page: the source filter is a group too, and counting it here would make
     this assert something it does not mean. */
  expect(container.querySelectorAll(".rail details").length).toBe(5);
});

test("queue and ingest start open, match and job start collapsed", async () => {
  renderPage();
  const openOf = (t: string) => (screen.getByText(t).closest("details") as HTMLDetailsElement).open;
  await screen.findByText("add to queue");
  expect(openOf("add to queue")).toBe(true);
  expect(openOf("ingest selection")).toBe(true);
  expect(openOf("profile match")).toBe(false);
  expect(openOf("job progress")).toBe(false);
});

test("the ingest action renders outside the rail's scroll region", async () => {
  const { container } = renderPage();
  await screen.findByText("add to queue");
  const footer = container.querySelector(".rail-footer");
  const scroll = container.querySelector(".rail-scroll");
  const ingest = [...container.querySelectorAll("button")].find(
    (b) => b.textContent?.trim() === "ingest",
  );
  expect(footer).toBeTruthy();
  expect(ingest && footer?.contains(ingest)).toBe(true);
  expect(ingest && scroll?.contains(ingest)).toBe(false);
});

test("the selected count renders in the pinned footer", async () => {
  const { container } = renderPage();
  await screen.findByText("add to queue");
  const footer = container.querySelector(".rail-footer");
  expect(footer?.querySelector(".selcount")).toBeTruthy();
});
