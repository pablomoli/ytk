import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const profileData = {
  generated_at: "2026-07-18T18:00:00+00:00",
  note_count: 134,
  embedding_model: "Qwen/Qwen3-Embedding-0.6B",
  profile_markdown: "You are an engineer-maker.\n\nYour throughline is mechanism.",
  claims: [
    { text: "You are an engineer-maker.", evidence_ids: ["a"] },
    { text: "Your throughline is mechanism.", evidence_ids: ["b"] },
  ],
  themes: [
    {
      id: "agentic-ai-coding-craft",
      label: "Agentic AI coding craft",
      summary: "Subagent orchestration and deterministic gates recur.",
      weight: 0.35,
      n_notes: 36,
      fresh_notes: 9,
      exemplars: [{ title: "Verifier subagents in practice", source: "youtube" }],
    },
    {
      id: "gpu-creative-coding",
      label: "GPU & creative coding",
      summary: "Shader techniques recur.",
      weight: 0.2,
      n_notes: 20,
      fresh_notes: 0,
      exemplars: [],
    },
  ],
};

vi.mock("../api/profile", () => ({
  useProfile: () => ({ isLoading: false, isError: false, data: profileData }),
  useRunProfile: () => ({ mutate: () => {}, isPending: false, isError: false }),
}));

import { Route } from "./profile";

function renderPage() {
  const Page = (Route as unknown as { options: { component: React.ComponentType } }).options
    .component;
  return render(<Page />);
}

test("renders concrete category rows with counts", () => {
  const { container } = renderPage();
  const rows = container.querySelector(".profile-themes");
  expect(rows?.textContent).toContain("Agentic AI coding craft");
  expect(screen.getByText(/35% · 36 notes · 9 recent/)).toBeInTheDocument();
  expect(screen.getByText(/20% · 20 notes$/)).toBeInTheDocument(); // no "0 recent"
});

test("exemplars carry a provenance icon", () => {
  const { container } = renderPage();
  const exemplar = container.querySelector(".profile-exemplar");
  expect(exemplar?.textContent).toContain("Verifier subagents in practice");
  expect(exemplar?.querySelector("svg")).not.toBeNull();
});

test("theme weight bar exposes meter semantics", () => {
  const { container } = renderPage();
  expect(container.querySelector(".profile-theme-bar")).toHaveAttribute("role", "meter");
});

test("renders the portrait prose below the categories", () => {
  const { container } = renderPage();
  const prose = container.querySelector(".profile-prose");
  expect(prose).not.toBeNull();
  expect(prose?.querySelectorAll("p")).toHaveLength(2);
  expect(screen.getByText("You are an engineer-maker.")).toBeInTheDocument();
  const themes = container.querySelector(".profile-themes");
  expect(themes!.compareDocumentPosition(prose!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("has no onboarding/self-explanation block", () => {
  const { container } = renderPage();
  expect(container.querySelector(".profile-intro")).toBeNull();
  expect(screen.queryByText(/attention weather/i)).toBeNull();
});
