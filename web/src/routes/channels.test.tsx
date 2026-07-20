import { render, screen, fireEvent } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mutate = vi.fn();
const channels = [
  { key: "youtube:syntax", source: "youtube", channel: "Syntax", count: 8,
    last_seen: "2026-07-10", top_tags: ["css", "ai"], notes: [], status: null },
  { key: "instagram:rndyrbrts", source: "instagram", channel: "rndyrbrts", count: 6,
    last_seen: "2026-07-09", top_tags: ["ai"], notes: [], status: "loved" },
];

vi.mock("../api/channels", () => ({
  useChannels: () => ({ isLoading: false, isError: false, data: channels }),
  useSetChannelStatus: () => ({ mutate }),
}));

import { Route } from "./channels";

function renderPage() {
  const Page = (Route as unknown as { options: { component: React.ComponentType } })
    .options.component;
  return render(<Page />);
}

test("groups creators by source with counts", () => {
  const { container } = renderPage();
  expect(screen.getByText("Syntax")).toBeInTheDocument();
  expect(screen.getByText("rndyrbrts")).toBeInTheDocument();
  const heads = [...container.querySelectorAll(".channel-group-head")].map((h) => h.textContent);
  expect(heads.join(" ")).toContain("youtube");
  expect(heads.join(" ")).toContain("instagram");
});

test("loved creator carries the loved class and pressed state", () => {
  const { container } = renderPage();
  const loved = container.querySelector(".channel-row.loved");
  expect(loved?.textContent).toContain("rndyrbrts");
  const btn = loved?.querySelector('button[aria-pressed="true"]');
  expect(btn?.textContent).toBe("love");
});

test("clicking love toggles status via the mutation", () => {
  renderPage();
  const row = screen.getByText("Syntax").closest(".channel-row")!;
  fireEvent.click(row.querySelector("button")!);
  expect(mutate).toHaveBeenCalledWith({ key: "youtube:syntax", status: "loved" });
});

test("header shows total and loved count", () => {
  renderPage();
  expect(screen.getByText(/2 creators · 1 loved/)).toBeInTheDocument();
});
