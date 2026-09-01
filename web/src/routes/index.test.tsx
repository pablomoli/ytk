import { render, screen, fireEvent } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mutate = vi.fn();
const asks = [
  {
    id: 1,
    ask_id: 11,
    item_id: 5,
    subkind: "transcript junk",
    created_at: "2026-08-30T01:00:00+00:00",
    title: "A garbled talk",
    url: "https://y/1",
    source: "youtube",
    proposal: {
      kind: "transcript junk",
      why: "auto-captions garbled (repetition 61%)",
      options: ["retry with Whisper", "keep with the warning", "drop"],
    },
  },
  {
    id: 2,
    ask_id: 12,
    item_id: 6,
    subkind: "intent missing",
    created_at: "2026-08-30T02:00:00+00:00",
    title: "A clean talk",
    url: "https://y/2",
    source: "youtube",
    proposal: {
      kind: "intent missing",
      why: "why this one?",
      options: ["intent", "reaction", "just want it", "drop"],
      window_days: 7,
    },
  },
];

let outbox: {
  isLoading: boolean;
  isError: boolean;
  refetch?: () => void;
  data?: unknown;
} = {
  isLoading: false,
  isError: false,
  data: {
    asks,
    speaks: [],
    parked: { count: 3, oldest: "2026-08-12T00:00:00+00:00" },
    loop: { ok: true, line: "last tick 13:00Z \u00b7 2 advanced \u00b7 0 errors" },
  },
};

vi.mock("../api/outbox", () => ({
  useOutbox: () => outbox,
  useAnswerAsk: () => ({ mutate, isPending: false }),
}));

import { Route } from "./index";

function renderPage() {
  const Page = (Route as unknown as { options: { component: React.ComponentType } }).options
    .component;
  return render(<Page />);
}

test("renders ask cards in delivery order with kind, title and why", () => {
  const { container } = renderPage();
  const cards = [...container.querySelectorAll("[data-ask]")];
  expect(cards).toHaveLength(2);
  expect(cards[0]!.textContent).toContain("transcript junk");
  expect(cards[0]!.textContent).toContain("A garbled talk");
  expect(cards[0]!.textContent).toContain("auto-captions garbled");
  expect(cards[1]!.textContent).toContain("intent missing");
});

test("clicking an option answers through the mutation", () => {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "retry with Whisper" }));
  expect(mutate).toHaveBeenCalledWith(
    expect.objectContaining({ ask_id: 11, choice: "retry with Whisper" }),
    expect.anything(),
  );
});

test("say-more opens a text field and sends choice with text", () => {
  renderPage();
  fireEvent.click(screen.getAllByRole("button", { name: "say more" })[0]!);
  const box = screen.getByRole("textbox");
  fireEvent.change(box, { target: { value: "keep it, the garble is the joke" } });
  fireEvent.click(screen.getByRole("button", { name: "answer" }));
  expect(mutate).toHaveBeenCalledWith(
    expect.objectContaining({ ask_id: 11, text: "keep it, the garble is the joke" }),
    expect.anything(),
  );
});

test("parked and loop lines render once each", () => {
  renderPage();
  expect(screen.getByText(/3 parked, oldest from/)).toBeInTheDocument();
  expect(screen.getByText(/2 advanced/)).toBeInTheDocument();
});

test("bounce ask renders the draft, the grader's objections, and the thumbnail", () => {
  outbox = {
    isLoading: false,
    isError: false,
    data: {
      asks: [
        {
          id: 3,
          ask_id: 31,
          item_id: 9,
          subkind: "grader bounce, twice",
          created_at: "2026-08-31T23:00:00+00:00",
          title: "How to Read Academic Papers",
          url: "https://y/9",
          source: "youtube",
          thumbnail: "https://i.ytimg.com/vi/x/hq720.jpg",
          draft: {
            thesis: "A six-step workflow for deep reading.",
            summary: "Front-load context, then alternate reads.",
            key_concepts: ["deep research report", "author interview"],
            insights: ["interview the first author"],
            take_response: "This answers your reading-list intent.",
          },
          objections: [
            { check: "concept grounding", detail: "'Empirical-field framing' not findable" },
          ],
          proposal: {
            kind: "grader bounce, twice",
            options: ["accept as is", "say what is wrong", "drop"],
          },
        },
      ],
      speaks: [],
      parked: { count: 0, oldest: null },
      loop: { ok: true, line: "ok" },
    },
  };
  const { container } = renderPage();
  expect(screen.getByText("How to Read Academic Papers")).toBeInTheDocument();
  expect(screen.getByText(/six-step workflow/)).toBeInTheDocument();
  expect(screen.getByText(/Front-load context/)).toBeInTheDocument();
  expect(screen.getByText(/deep research report/)).toBeInTheDocument();
  expect(screen.getByText(/not findable/)).toBeInTheDocument();
  const img = container.querySelector("img");
  expect(img?.getAttribute("src")).toBe("https://i.ytimg.com/vi/x/hq720.jpg");
});

test("inert loop line wears the warning tone", () => {
  outbox = {
    isLoading: false,
    isError: false,
    data: {
      asks: [],
      speaks: [],
      parked: { count: 0, oldest: null },
      loop: { ok: false, line: "inert \u2014 tripped: token ceiling; run `ytk loop resume`" },
    },
  };
  const { container } = renderPage();
  const strip = container.querySelector("[data-loop-strip]");
  expect(strip?.textContent).toContain("token ceiling");
  expect(strip?.className).toContain("text-accent");
});

test("empty outbox invites, not apologizes", () => {
  outbox = {
    isLoading: false,
    isError: false,
    data: {
      asks: [],
      speaks: [],
      parked: { count: 0, oldest: null },
      loop: { ok: true, line: "never ticked" },
    },
  };
  renderPage();
  expect(screen.getByText(/nothing needs you/i)).toBeInTheDocument();
});

test("digest polls while the loop is mid-verb (#199)", () => {
  vi.useFakeTimers();
  const refetch = vi.fn();
  outbox = {
    isLoading: false,
    isError: false,
    refetch,
    data: {
      asks: [],
      speaks: [],
      parked: { count: 0, oldest: null },
      loop: { ok: true, working: true, line: "enriching How to Read Papers · 40s" },
    },
  } as typeof outbox;
  renderPage();
  expect(screen.getByText(/enriching How to Read Papers/)).toBeInTheDocument();
  vi.advanceTimersByTime(6000);
  expect(refetch.mock.calls.length).toBeGreaterThanOrEqual(2);
  vi.useRealTimers();
});

test("digest does not poll when the loop is idle", () => {
  vi.useFakeTimers();
  const refetch = vi.fn();
  outbox = {
    isLoading: false,
    isError: false,
    refetch,
    data: {
      asks: [],
      speaks: [],
      parked: { count: 0, oldest: null },
      loop: { ok: true, working: false, line: "last tick 13:00Z" },
    },
  } as typeof outbox;
  renderPage();
  vi.advanceTimersByTime(10000);
  expect(refetch).not.toHaveBeenCalled();
  vi.useRealTimers();
});

test("answering opens a poll window so the strip catches the verb starting", () => {
  vi.useFakeTimers();
  const refetch = vi.fn();
  mutate.mockImplementation((_answer, opts) => opts?.onSuccess?.());
  outbox = {
    isLoading: false,
    isError: false,
    refetch,
    data: {
      asks,
      speaks: [],
      parked: { count: 3, oldest: null },
      loop: { ok: true, working: false, line: "last tick 13:00Z" },
    },
  } as typeof outbox;
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "retry with Whisper" }));
  vi.advanceTimersByTime(6000);
  expect(refetch.mock.calls.length).toBeGreaterThanOrEqual(2);
  mutate.mockReset();
  vi.useRealTimers();
});

const connectionsAsk = {
  id: 4,
  ask_id: 41,
  item_id: 12,
  subkind: "connections",
  created_at: "2026-08-31T23:30:00+00:00",
  title: "How to Read Deep Learning Papers",
  url: "https://y/12",
  source: "youtube",
  proposal: {
    kind: "connections",
    why: "2 related notes argued",
    options: ["approve", "strike some", "none"],
    links: [
      { target: "paper-notes", target_title: "Paper Notes", argument: "same margin-question triage" },
      { target: "loop-video", target_title: "Loop Video", argument: "both gate work behind a judge" },
    ],
  },
};

function renderConnections() {
  outbox = {
    isLoading: false,
    isError: false,
    data: {
      asks: [connectionsAsk],
      speaks: [],
      parked: { count: 0, oldest: null },
      loop: { ok: true, working: false, line: "ok" },
    },
  };
  return renderPage();
}

test("connections card renders each link checked with its argument (#197 P6)", () => {
  renderConnections();
  const boxes = screen.getAllByRole("checkbox");
  expect(boxes).toHaveLength(2);
  boxes.forEach((b) => expect(b).toBeChecked());
  expect(screen.getByText(/same margin-question triage/)).toBeInTheDocument();
  expect(screen.getByText(/\[\[paper-notes\]\]/)).toBeInTheDocument();
});

test("all links kept answers approve without text", () => {
  mutate.mockClear();
  renderConnections();
  fireEvent.click(screen.getByRole("button", { name: "approve" }));
  expect(mutate).toHaveBeenCalledWith(
    { ask_id: 41, choice: "approve" },
    expect.anything(),
  );
});

test("striking one link answers strike some with the survivors as JSON", () => {
  mutate.mockClear();
  renderConnections();
  fireEvent.click(screen.getByRole("checkbox", { name: "link paper-notes" }));
  fireEvent.click(screen.getByRole("button", { name: "approve 1 of 2" }));
  expect(mutate).toHaveBeenCalledWith(
    { ask_id: 41, choice: "strike some", text: JSON.stringify(["loop-video"]) },
    expect.anything(),
  );
});

test("striking every link sends none", () => {
  mutate.mockClear();
  renderConnections();
  for (const box of screen.getAllByRole("checkbox")) fireEvent.click(box);
  fireEvent.click(screen.getByRole("button", { name: "none survive" }));
  expect(mutate).toHaveBeenCalledWith({ ask_id: 41, choice: "none" }, expect.anything());
});

test("connections card hides the generic option buttons", () => {
  renderConnections();
  expect(screen.queryByRole("button", { name: "strike some" })).toBeNull();
  expect(screen.queryByRole("button", { name: "say more" })).toBeNull();
});
