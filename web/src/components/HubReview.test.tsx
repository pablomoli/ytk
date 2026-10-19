import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { HubCandidate, HubList } from "../api/hubs";

const api = vi.hoisted(() => ({
  list: { data: undefined as HubList | undefined, isPending: false, isError: false, error: null },
  apply: { isPending: false, mutate: vi.fn() },
}));

vi.mock("../api/hubs", () => ({
  useHubList: () => api.list,
  useApplyHubVerdicts: () => api.apply,
}));

import { HubReview } from "./HubReview";

const cand = (over: Partial<HubCandidate>): HubCandidate => ({
  kind: "concept",
  key: "manim",
  name: "Manim",
  count: 19,
  examples: ["Alpha", "Beta"],
  target: "Manim",
  target_path: "second-brain/links/concepts/Manim.md",
  hand_made: false,
  collision: "",
  verdict: "pending",
  judged_at: "",
  ...over,
});

const summary = {
  concept: { names: 2, notes: 20, pending: 2, approve: 0, strike: 0 },
  creator: { names: 2, notes: 9, pending: 1, approve: 1, strike: 0 },
};

beforeEach(() => {
  api.list.data = {
    threshold: 2,
    summary,
    candidates: [
      cand({}),
      cand({ key: "fable", name: "Fable", count: 11, examples: ["A model", "A story"] }),
      cand({
        kind: "creator",
        key: "dwarkesh patel",
        name: "Dwarkesh Patel",
        count: 19,
        hand_made: true,
        target: "Dwarkesh Patel",
        target_path: "second-brain/notes/ai/people/Dwarkesh Patel.md",
      }),
      cand({ kind: "creator", key: "syntax", name: "Syntax", count: 12, verdict: "approve" }),
    ],
  };
  api.apply.mutate.mockReset();
});

afterEach(() => vi.clearAllMocks());

test("lists pending names with counts, examples and where each would link", () => {
  render(<HubReview />);
  const fable = screen.getByRole("listitem", { name: "concept Fable" });
  expect(fable).toHaveTextContent("11 notes");
  expect(fable).toHaveTextContent("A model · A story");
  expect(screen.getByRole("listitem", { name: "creator Dwarkesh Patel" })).toHaveTextContent(
    "links to your note second-brain/notes/ai/people/Dwarkesh Patel.md",
  );
  // the pending view hides names already judged
  expect(screen.queryByRole("listitem", { name: "creator Syntax" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Apply hub list" })).toBeNull();
});

test("strike and approve-pending send only the changed verdicts after confirmation", async () => {
  render(<HubReview />);
  const fable = screen.getByRole("listitem", { name: "concept Fable" });
  fireEvent.click(within(fable).getByRole("radio", { name: "strike" }));
  fireEvent.click(screen.getByRole("button", { name: "Approve pending shown" }));
  expect(screen.getByText("2 to approve, 1 to strike")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Apply hub list" }));
  expect(api.apply.mutate).not.toHaveBeenCalled();
  const dialog = screen.getByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Apply hub list" }));
  await waitFor(() => expect(api.apply.mutate).toHaveBeenCalledTimes(1));
  expect(api.apply.mutate.mock.calls[0][0]).toEqual([
    { kind: "concept", key: "manim", verdict: "approve" },
    { kind: "concept", key: "fable", verdict: "strike" },
    { kind: "creator", key: "dwarkesh patel", verdict: "approve" },
  ]);
});

test("an approved name can be struck later from the approved view", () => {
  render(<HubReview />);
  fireEvent.click(screen.getByRole("radio", { name: "approved" }));
  const syntax = screen.getByRole("listitem", { name: "creator Syntax" });
  expect(within(syntax).getByRole("radio", { name: "approve" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  fireEvent.click(within(syntax).getByRole("radio", { name: "strike" }));
  expect(screen.getByText("0 to approve, 1 to strike")).toBeInTheDocument();
});
