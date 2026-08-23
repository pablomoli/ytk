import { act, fireEvent, render, screen } from "@testing-library/react";
import { page } from "vitest/browser";
import { beforeEach, expect, test, vi } from "vitest";
import type { JobStatus } from "../api/job";
import { TooltipProvider } from "../components/ui/tooltip";

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
  /* Real CSS hides .masonry children until the real grid stamps data-placed;
     the mock stamps it via wrappers so cards reach the accessibility tree. */
  MasonryGrid: ({ children }: { children: React.ReactNode }) => (
    <main className="masonry">
      {(Array.isArray(children) ? children : [children]).map((c, i) => (
        <div data-placed="1" key={i}>
          {c}
        </div>
      ))}
    </main>
  ),
}));
vi.mock("../lib/useInfiniteWindow", () => ({
  useInfiniteWindow: (items: unknown[]) => ({ visible: items, sentinelRef: vi.fn() }),
}));

const startRank = vi.fn();
const ingestMutate = vi.fn();
const idleJob: JobStatus = {
  running: false,
  total: 0,
  done: 0,
  current: null,
  current_started: null,
  queued: [],
  failures: [],
  annotated: 0,
  linked: [],
};
let jobQuery = { data: idleJob };
const queue = [
  { url: "new", source: "tiktok", text: "Newest ordinary item", shared_at: "2026-07-20" },
  { url: "match", source: "tiktok", text: "Strong profile match", shared_at: "2026-07-01" },
  { url: "other-match", source: "pinterest", text: "Other profile match", shared_at: "2026-06-01" },
  // Hidden by default (#126), so it is only in the grid when asked for.
  { url: "red", source: "reddit", text: "Reddit item", shared_at: "2026-05-01" },
  // Carries a reflection question (#98).
  {
    url: "flagged",
    source: "tiktok",
    text: "Flagged item",
    author: "ana",
    shared_at: "2026-04-01",
    reflection_question: "why does this matter to you?",
    reflection_answered: false,
  },
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
  useJobStatus: () => jobQuery,
}));
vi.mock("../api/mutations", () => ({
  useAddUrls: () => ({ mutate: vi.fn(), isPending: false }),
  useRefreshSources: () => ({ mutate: vi.fn(), isPending: false }),
  useIngest: () => ({ mutate: ingestMutate, isPending: false }),
  // Card imports this from the same module; the factory must supply it too.
  reflectAnswer: vi.fn(async () => ({ stored: true })),
}));
vi.mock("../api/profileRank", () => ({
  useProfileRank: () => rankQuery,
  useStartProfileRank: () => ({ mutate: startRank, isPending: false }),
}));

import { Route } from "./inbox";

function renderPage() {
  const Page = (Route as unknown as { options: { component: React.ComponentType } }).options
    .component;
  return render(
    <TooltipProvider delayDuration={0}>
      <div className="hub-shell">
        <main className="hub-outlet">
          <Page />
        </main>
      </div>
    </TooltipProvider>,
  );
}

const SHOW_MATCHES_KEY = "ytk:inbox:show-profile-matches";
const enableMatches = () => localStorage.setItem(SHOW_MATCHES_KEY, "1");

beforeEach(() => {
  routeSearch = {};
  rankQuery = { data: completedRank, isError: false };
  startRank.mockClear();
  ingestMutate.mockClear();
  jobQuery = { data: idleJob };
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

/* #126 hid reddit at the view; the demotion removed it as a pull source, so
   nothing is hidden any more. A pre-demotion row left in the queue shows up
   like any other rather than needing to be asked for. */
test("shows a leftover reddit item without being asked", () => {
  const { container } = renderPage();
  const text = [...container.querySelectorAll(".masonry .card")].map((c) => c.textContent);
  expect(text.join(" ")).toContain("Reddit item");
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

/* --- #98: rail reflection question --- */

const selectCard = (label: string) =>
  fireEvent.click(screen.getByRole("checkbox", { name: `Select ${label}` }));
const ingestButton = () => screen.getByRole("button", { name: /ingest \d+ items?/i });

test("selecting a flagged item surfaces its question above the thought box", () => {
  renderPage();
  expect(screen.queryByTestId("rail-reflection")).not.toBeInTheDocument();

  selectCard("Newest ordinary item");
  expect(screen.queryByTestId("rail-reflection")).not.toBeInTheDocument();

  selectCard("Flagged item");
  const block = screen.getByTestId("rail-reflection");
  expect(block).toHaveTextContent("why does this matter to you?");
  // Addressed by the item's title/author line.
  expect(block).toHaveTextContent("Flagged item");
  expect(block).toHaveTextContent("ana");
  // Above the existing thought box.
  const thought = screen.getByLabelText("Thought");
  expect(block.compareDocumentPosition(thought) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("the reflection answer joins the ingest payload keyed by url", () => {
  renderPage();
  selectCard("Flagged item");
  fireEvent.change(screen.getByLabelText("Reflection"), {
    target: { value: "it tracks my craft" },
  });
  fireEvent.click(ingestButton());

  expect(ingestMutate).toHaveBeenCalledTimes(1);
  expect(ingestMutate.mock.calls[0][0]).toMatchObject({
    urls: ["flagged"],
    reflections: { flagged: "it tracks my craft" },
  });
});

test("ingesting with the answer empty sends no reflections key", () => {
  renderPage();
  selectCard("Flagged item");
  fireEvent.click(ingestButton());

  expect(ingestMutate).toHaveBeenCalledTimes(1);
  expect(ingestMutate.mock.calls[0][0]).not.toHaveProperty("reflections");
});

test("zero selection hides the ingest composer and its actions", async () => {
  const { container } = renderPage();
  await screen.findAllByRole("group");
  expect(container.querySelectorAll(".rail details")).toHaveLength(3);
  expect(screen.queryByText("ingest selection")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Thought")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /ingest \d+ items?/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /clear selection/i })).not.toBeInTheDocument();
});

test("selection reveals one contextual composer and combined ingest action", async () => {
  const { container } = renderPage();
  selectCard("Newest ordinary item");

  expect(container.querySelectorAll(".rail details")).toHaveLength(4);
  expect(screen.getByText("ingest selection")).toBeInTheDocument();
  expect(screen.getByLabelText("Thought")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Ingest 1 item" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Clear selection" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "design" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("queue starts open while profile match starts collapsed", async () => {
  renderPage();
  const openOf = (t: string) => (screen.getByText(t).closest("details") as HTMLDetailsElement).open;
  await screen.findByText("add to queue");
  expect(openOf("add to queue")).toBe(true);
  expect(openOf("profile match")).toBe(false);
});

test("running progress stays above the rail scroller", async () => {
  jobQuery = {
    data: {
      ...idleJob,
      running: true,
      total: 4,
      done: 1,
      current: "new",
      current_started: Math.floor(Date.now() / 1000) - 17,
      queued: ["match", "other-match", "flagged"],
    },
  };
  const { container } = renderPage();
  const progress = screen.getByLabelText("Ingest job progress");
  const scroll = container.querySelector(".rail-scroll");
  const rail = screen.getByRole("complementary", { name: "Inbox controls" });

  expect(progress).toHaveTextContent("3 items remaining");
  expect(progress).toHaveTextContent("elapsed");
  expect(progress).not.toHaveTextContent(/\d+\/\d+/);
  expect(progress).not.toHaveTextContent(/~2 min|minute or two/i);
  expect(rail).toContainElement(progress);
  expect(scroll).not.toContainElement(progress);
  expect(progress.nextElementSibling).toBe(scroll);
});

test("the ingest action renders outside the rail's scroll region", async () => {
  const { container } = renderPage();
  selectCard("Newest ordinary item");
  const footer = container.querySelector(".rail-footer");
  const scroll = container.querySelector(".rail-scroll");
  const ingest = screen.getByRole("button", { name: "Ingest 1 item" });
  expect(footer).toContainElement(ingest);
  expect(scroll).not.toContainElement(ingest);
});

test("clear selection hides the composer without discarding its draft", () => {
  renderPage();
  selectCard("Newest ordinary item");
  fireEvent.change(screen.getByLabelText("Thought"), { target: { value: "keep this draft" } });
  fireEvent.click(screen.getByRole("button", { name: "design" }));

  fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
  expect(screen.queryByLabelText("Thought")).not.toBeInTheDocument();

  selectCard("Newest ordinary item");
  expect(screen.getByLabelText("Thought")).toHaveValue("keep this draft");
  expect(screen.getByRole("button", { name: "design" })).toHaveAttribute("aria-pressed", "true");
});

test("drafts clear only after ingest succeeds", () => {
  renderPage();
  selectCard("Flagged item");
  fireEvent.change(screen.getByLabelText("Thought"), { target: { value: "a useful note" } });
  fireEvent.change(screen.getByLabelText("Reflection"), { target: { value: "because it matters" } });
  fireEvent.click(screen.getByRole("button", { name: "design" }));
  fireEvent.click(ingestButton());

  expect(screen.getByLabelText("Thought")).toHaveValue("a useful note");
  expect(screen.getByLabelText("Reflection")).toHaveValue("because it matters");

  const options = ingestMutate.mock.calls[0][1] as { onSuccess: () => void };
  act(() => options.onSuccess());
  expect(screen.queryByLabelText("Thought")).not.toBeInTheDocument();

  selectCard("Flagged item");
  expect(screen.getByLabelText("Thought")).toHaveValue("");
  expect(screen.getByLabelText("Reflection")).toHaveValue("");
  expect(screen.getByRole("button", { name: "design" })).toHaveAttribute("aria-pressed", "false");
});

test("queue inputs use visible labels and example placeholders", () => {
  renderPage();
  const urls = screen.getByLabelText("URLs");
  expect(urls).toHaveAttribute("placeholder", expect.stringMatching(/^example:/i));
  expect(screen.getByText("URLs").tagName).toBe("LABEL");
});

test.each([
  [375, 812],
  [390, 844],
  [760, 900],
  [761, 900],
  [768, 1024],
  [1440, 900],
])("keeps progress, selection action, and cards reachable at %ix%i", async (width, height) => {
  await page.viewport(width, height);
  jobQuery = {
    data: {
      ...idleJob,
      running: true,
      total: 4,
      done: 1,
      current: "new",
      current_started: Math.floor(Date.now() / 1000) - 17,
      queued: ["match", "other-match", "flagged"],
    },
  };
  renderPage();
  selectCard("Reddit item");

  expect(screen.getByLabelText("Ingest job progress")).toBeInViewport();
  expect(screen.getByRole("button", { name: "Ingest 1 item" })).toBeInViewport();
  expect(screen.getByText("Reddit item").closest(".card")).toBeInViewport();
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);

  await page.viewport(1024, 768);
});
