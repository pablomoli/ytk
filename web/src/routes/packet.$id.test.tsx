import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { ReactElement } from "react";
import type { Packet } from "../api/packet";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({
    options,
    useParams: () => ({ id: "534" }),
    useSearch: () => ({}),
  }),
}));

const packet: Packet = {
  id: 534,
  title: "the two ffp hosts",
  source: "instagram",
  url: "https://www.instagram.com/reel/x",
  t: "2026-09-06T22:20:00+00:00",
  state: "asking",
  station: {
    name: "owner",
    since: "2026-09-06T22:16:40+00:00",
    note: "ask · grader bounce, twice",
    model: false,
  },
  calls: 9,
  cap: 8,
  tokens: 12_345,
  rounds: 2,
  running: false,
  take: { kind: "intent", text: "why the wigs" },
  view: {
    hash: "993960c5f71f",
    bundle: "b216b24e3101",
    source: "instagram",
    origin: "whisper",
    duration: 82,
    nlines: 30,
    lines: [
      { s: 0, text: "welcome to the show", hit: false },
      { s: 3, text: "two hosts in rainbow wigs", hit: true },
      { fold: 20 },
      { s: 40, text: "the tricorn is a mirror", hit: false },
    ],
    shown: ["t:0-82", "frame:001"],
    openable: [],
    not_shown: ["frames 2 to 45 (44 frames)"],
    gaps: [],
    budget: { frames_shown: 2, evidence_cap_chars: 400_000, sheet: "shown" },
    tokenizer: "ascii-words-folded-stemmed-v2",
    nframes: 45,
    frames: [{ id: "frame:001", t: null, shown: true, url: "/api/evidence/frame/534/1" }],
  },
  agreement: { status: "mismatch", draft: "993960c5f71f", grade: "aaaaaaaaaaaa" },
  attempts: [
    {
      n: 1,
      opened_at: "2026-09-06T22:13:00+00:00",
      closed_at: "2026-09-06T22:14:00+00:00",
      view_hash: "993960c5f71f",
      take_kind: "intent",
      findings: [],
      passed: false,
      layer: "model",
      bounces: [{ check: "grounding", where: "summary, t:3", detail: "one wig" }],
      spots: [{ grounded: true, where: "t:40", claim: "mirror" }],
      draft: { thesis: "A reel.", concepts: 2, insights: 1, moments: 0, tags: ["math"] },
      writer: {
        model: "claude-sonnet-5",
        tokens: 2000,
        seconds: 24,
        at: "2026-09-06T22:13:30+00:00",
        view_hash: "993960c5f71f",
      },
      marker: {
        model: "claude-opus-5",
        tokens: 4000,
        seconds: 50,
        at: "2026-09-06T22:14:00+00:00",
        view_hash: "aaaaaaaaaaaa",
      },
    },
    {
      n: 2,
      opened_at: "2026-09-06T22:15:00+00:00",
      closed_at: "2026-09-06T22:16:00+00:00",
      view_hash: "993960c5f71f",
      take_kind: "intent",
      findings: [{ check: "grounding", where: "summary, t:3", detail: "one wig" }],
      passed: false,
      layer: "model",
      bounces: [{ check: "thesis", where: "thesis", detail: "historical fact" }],
      spots: [],
      draft: { thesis: "A better reel.", concepts: 3, insights: 1, moments: 1, tags: [] },
      writer: {
        model: "claude-sonnet-5",
        tokens: 2100,
        seconds: 30,
        at: "2026-09-06T22:15:30+00:00",
        view_hash: "993960c5f71f",
      },
      marker: {
        model: "claude-opus-5",
        tokens: 3000,
        seconds: 40,
        at: "2026-09-06T22:16:00+00:00",
        view_hash: "993960c5f71f",
      },
    },
  ],
  asks: [
    {
      id: 59,
      kind: "grader bounce, twice",
      why: "Thesis: the sentence states a historical fact",
      options: ["accept", "say what is wrong", "drop"],
      created_at: "2026-09-06T22:16:40+00:00",
      attempt: 2,
      view_hash: "993960c5f71f",
      links: [],
      answer: null,
    },
  ],
  trail: Array.from({ length: 10 }, (_, i) => ({
    at: `2026-09-06T22:1${Math.min(9, i)}:00+00:00`,
    who: i % 2 ? "teacher" : "student",
    what: `row ${i}`,
    right: "",
    error: false,
    model: false,
    tokens: 0,
  })),
  commands: {
    view: "ytk view 534 --attempt 2 --full",
    grade: "ytk grade 534 --attempt 2",
    item: "ytk item 534",
  },
};

const mutate = vi.fn();
vi.mock("../api/outbox", () => ({
  useAnswerAsk: () => ({ mutate, isPending: false, isError: false, error: null }),
}));
const packetState: { data: Packet; isError: boolean; error: null; refetch: () => void } = {
  data: packet,
  isError: false,
  error: null,
  refetch: vi.fn(),
};
vi.mock("../api/packet", async () => ({
  ...(await vi.importActual<typeof import("../api/packet")>("../api/packet")),
  usePacket: () => packetState,
}));

async function mount() {
  const mod = await import("./packet.$id");
  const Page = (mod.Route as unknown as { options: { component: () => ReactElement } }).options
    .component;
  return render(<Page />);
}

test("the header carries station, pad past the cap and the packet agreement", async () => {
  await mount();
  expect(screen.getByTestId("station")).toHaveTextContent("owner");
  expect(screen.getByText(/9 calls, 1 past the pad of 8/)).toBeInTheDocument();
  const agreement = screen.getByTestId("agreement");
  expect(agreement).toHaveTextContent("packet mismatch");
  expect(agreement).toHaveTextContent("draft 993960c5f71f · grade aaaaaaaaaaaa");
  expect(screen.getByText(/the sticky note, intent: why the wigs/)).toBeInTheDocument();
});

test("the latest round is open and earlier rounds fold to one line", async () => {
  const { container } = await mount();
  const r1 = container.querySelector('[data-round="1"]')!;
  const r2 = container.querySelector('[data-round="2"]')!;
  expect(r1.getAttribute("data-folded")).toBe("1");
  expect(r2.getAttribute("data-folded")).toBe("0");
  expect(within(r2 as HTMLElement).getByText("A better reel.")).toBeInTheDocument();
  fireEvent.click(within(r1 as HTMLElement).getByRole("button", { expanded: false }));
  expect(r1.getAttribute("data-folded")).toBe("0");
  expect(within(r1 as HTMLElement).getByText(/differs from aaaaaaaaaaaa/)).toBeInTheDocument();
});

test("an open ask answers through the outbox path, by click and by key", async () => {
  mutate.mockClear();
  await mount();
  fireEvent.click(screen.getByRole("button", { name: /accept/ }));
  expect(mutate).toHaveBeenCalledWith({ ask_id: 59, choice: "accept" }, expect.anything());
  fireEvent.keyDown(window, { key: "3" });
  expect(mutate).toHaveBeenLastCalledWith({ ask_id: 59, choice: "drop" }, expect.anything());
  fireEvent.keyDown(window, { key: "2" });
  const box = screen.getByPlaceholderText(/what is wrong/);
  fireEvent.change(box, { target: { value: "one wig, not two" } });
  fireEvent.keyDown(box, { key: "Enter" });
  expect(mutate).toHaveBeenLastCalledWith(
    { ask_id: 59, choice: "say what is wrong", text: "one wig, not two" },
    expect.anything(),
  );
});

test("a cited second lights its transcript line; a frame opens the lightbox", async () => {
  const { container } = await mount();
  const line = container.querySelector('[data-second="40"]')!;
  line.scrollIntoView = vi.fn();
  const r2 = container.querySelector('[data-round="1"]') as HTMLElement;
  fireEvent.click(within(r2).getByRole("button", { expanded: false }));
  fireEvent.click(within(r2).getByRole("button", { name: "t:40" }));
  expect(line.className).toMatch(/bg-live/);
  expect(container.querySelector('[data-second="3"]')!.className).toMatch(/bg-accent/);
  fireEvent.click(screen.getByRole("button", { name: "open frame:001" }));
  expect(screen.getByText(/frame:001 · packet 993960c5f71f/)).toBeInTheDocument();
});

test("the trail shows the last eight until asked for all", async () => {
  await mount();
  expect(screen.queryByText("student · row 0")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "show all" }));
  expect(screen.getByText("student · row 0")).toBeInTheDocument();
});

test("a connections ask answers with the survivors; an intent ask carries words", async () => {
  mutate.mockClear();
  packetState.data = {
    ...packet,
    asks: [
      {
        id: 70,
        kind: "intent missing",
        why: "why this one?",
        options: ["intent", "reaction", "just want it", "drop"],
        created_at: "2026-09-06T22:16:40+00:00",
        attempt: null,
        view_hash: null,
        links: [],
        answer: null,
      },
      {
        id: 71,
        kind: "connections",
        why: "2 related notes argued",
        options: ["approve", "strike some", "none"],
        created_at: "2026-09-06T22:17:40+00:00",
        attempt: null,
        view_hash: null,
        links: [
          {
            target: "footage-first-method",
            title: "Footage-first method",
            why: "how visuals get made",
          },
          {
            target: "rndyrbrts-visual-language",
            title: "Visual language",
            why: "a spec for the look",
          },
        ],
        answer: null,
      },
    ],
  };
  await mount();
  fireEvent.click(screen.getByRole("button", { name: "say more" }));
  fireEvent.change(screen.getByPlaceholderText(/your words ride/), {
    target: { value: "for the visuals" },
  });
  fireEvent.click(screen.getByRole("button", { name: /intent/ }));
  expect(mutate).toHaveBeenLastCalledWith(
    { ask_id: 70, choice: "intent", text: "for the visuals" },
    expect.anything(),
  );
  fireEvent.click(screen.getByRole("checkbox", { name: "link rndyrbrts-visual-language" }));
  fireEvent.click(screen.getByRole("button", { name: "approve 1 of 2" }));
  expect(mutate).toHaveBeenLastCalledWith(
    { ask_id: 71, choice: "strike some", text: JSON.stringify(["footage-first-method"]) },
    expect.anything(),
  );
  fireEvent.click(screen.getByRole("button", { name: "none" }));
  expect(mutate).toHaveBeenLastCalledWith({ ask_id: 71, choice: "none" }, expect.anything());
  packetState.data = packet;
});

test("the open round follows the station's verb", async () => {
  packetState.data = {
    ...packet,
    station: { name: "teacher", since: "2026-09-06T22:16:40+00:00", note: "marking", model: true },
    attempts: [{ ...packet.attempts[1]!, closed_at: null, passed: null, marker: null }],
  };
  const { container } = await mount();
  expect(container.querySelector('[data-round="2"]')!.textContent).toMatch(/attempt 2\s*marking/);
  packetState.data = packet;
});
