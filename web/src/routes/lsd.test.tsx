import { act, render, screen, fireEvent } from "@testing-library/react";
import { expect, test, vi, beforeEach } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

type LsdCard = import("../api/lsd").LsdCard;
const cards: LsdCard[] = [
  {
    id: "r-0-build",
    kind: "build",
    title: "Hidden-State Doodler",
    body: "A tool where constrained doodles are observations.",
    parents: [
      { id: "a", title: "What is Applied Math, Really?" },
      { id: "b", title: "WigglyPaint hex-color trick" },
    ],
    extra: { bridge: "same shape", trail: ["step one", "step two"], question: "why?" },
  },
  {
    id: "r-1-post",
    kind: "post",
    title: "Why does typing a hex code feel like solving a mystery?",
    body: "Constraint-based pedagogy.",
    parents: [
      { id: "c", title: "C" },
      { id: "d", title: "D" },
    ],
  },
];

const mutate = vi.fn();
const state = { ratings: {} as Record<string, number>, isPending: false, isError: false };

vi.mock("../api/lsd", () => ({
  useLsdRuns: () => ({ data: [{ run_id: "r", cards: 2, rated: 0 }], isLoading: false, isError: false }),
  useLsdDeck: () => ({ data: { run_id: "r", cards, ratings: state.ratings }, isLoading: false, isError: false }),
  useRateCard: () => ({ mutate, isPending: state.isPending, isError: state.isError, error: null }),
}));

import { Route } from "./lsd";

const Page = (Route as unknown as { options: { component: () => React.JSX.Element } }).options.component;

beforeEach(() => {
  mutate.mockReset();
  state.ratings = {};
});

test("shows the first unrated card with its kind and hides the parents", () => {
  render(<Page />);
  expect(screen.getByRole("heading", { name: "Hidden-State Doodler" })).toBeInTheDocument();
  expect(screen.getByText("build")).toBeInTheDocument();
  expect(screen.queryByText("What is Applied Math, Really?")).not.toBeInTheDocument();
  expect(screen.queryByText("same shape")).not.toBeInTheDocument();
  expect(screen.getByText("did this show you something you had not seen?")).toBeInTheDocument();
  expect(screen.getByText("0 of 2 rated")).toBeInTheDocument();
});

test("rating sends the score and only then reveals the parents", () => {
  render(<Page />);
  fireEvent.click(screen.getByRole("radio", { name: "score 4" }));
  expect(mutate).toHaveBeenCalledTimes(1);
  expect(mutate.mock.calls[0][0]).toEqual({ run_id: "r", candidate_id: "r-0-build", score: 4, note: "" });
  expect(screen.queryByText("What is Applied Math, Really?")).not.toBeInTheDocument();
  const opts = mutate.mock.calls[0][1] as { onSuccess: () => void };
  act(() => opts.onSuccess());
  expect(screen.getByText("What is Applied Math, Really?")).toBeInTheDocument();
  expect(screen.getByText("WigglyPaint hex-color trick")).toBeInTheDocument();
  expect(screen.getByText("same shape")).toBeInTheDocument();
  expect(screen.getByText("step two")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "next" })).toBeInTheDocument();
});

test("rated cards are skipped and the empty deck says so", () => {
  state.ratings = { "r-0-build": 5 };
  render(<Page />);
  expect(screen.getByText("1 of 2 rated")).toBeInTheDocument();
  expect(screen.getByText("post")).toBeInTheDocument();
  state.ratings = { "r-0-build": 5, "r-1-post": 2 };
  render(<Page />);
  expect(screen.getByText("Deck rated")).toBeInTheDocument();
});

test("number keys rate the current card", () => {
  render(<Page />);
  fireEvent.keyDown(window, { key: "5" });
  expect(mutate).toHaveBeenCalledTimes(1);
  expect((mutate.mock.calls[0][0] as { score: number }).score).toBe(5);
});
