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
