import { render, screen, fireEvent } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mutate = vi.fn();
const recs = [
  {
    key: "tmdb:movie:438631",
    kind: "movie",
    title: "Dune",
    year: 2021,
    creator: "Denis Villeneuve",
    poster: "https://example.com/dune.jpg",
    rating: 8.1,
    overview: "Sand.",
    external_url: null,
    count: 5,
    sources: [{ title: "A note", path: "notes/a.md" }],
    status: null,
  },
  {
    key: "tmdb:show:1396",
    kind: "show",
    title: "Breaking Bad",
    year: 2008,
    creator: "Vince Gilligan",
    poster: null,
    rating: null,
    overview: null,
    external_url: null,
    count: 3,
    sources: [],
    status: "want",
  },
  {
    key: "hardcover:book:42",
    kind: "book",
    title: "Dune (novel)",
    year: 1965,
    creator: "Frank Herbert",
    poster: null,
    rating: 9.0,
    overview: null,
    external_url: null,
    count: 2,
    sources: [],
    status: null,
  },
];

vi.mock("../api/recs", () => ({
  useRecs: () => ({ isLoading: false, isError: false, data: recs }),
  useSetRecStatus: () => ({ mutate }),
}));

import { Route } from "./recs";

function renderPage() {
  const Page = (Route as unknown as { options: { component: React.ComponentType } })
    .options.component;
  return render(<Page />);
}

function cardByTitle(container: HTMLElement, title: string): HTMLElement | null {
  const heads = [...container.querySelectorAll<HTMLElement>(".rec-title")];
  return heads.find((h) => h.textContent === title)?.closest(".rec-card") ?? null;
}

test("renders watch cards with titles by default", () => {
  const { container } = renderPage();
  expect(cardByTitle(container, "Dune")).not.toBeNull();
  expect(cardByTitle(container, "Breaking Bad")).not.toBeNull();
  expect(cardByTitle(container, "Dune (novel)")).toBeNull();
});

test("switching to the read tab shows read kinds", () => {
  const { container } = renderPage();
  fireEvent.click(screen.getByRole("tab", { name: /read/i }));
  expect(cardByTitle(container, "Dune (novel)")).not.toBeNull();
  expect(cardByTitle(container, "Breaking Bad")).toBeNull();
});

test("clicking a status button calls the mutation with key and status", () => {
  const { container } = renderPage();
  const card = cardByTitle(container, "Dune")!;
  const wantBtn = [...card.querySelectorAll("button")].find((b) => b.textContent === "want")!;
  fireEvent.click(wantBtn);
  expect(mutate).toHaveBeenCalledWith({ key: "tmdb:movie:438631", status: "want" });
});

test("null-poster card renders a text fallback, not a broken image", () => {
  const { container } = renderPage();
  const card = cardByTitle(container, "Breaking Bad")!;
  expect(card.querySelector("img")).toBeNull();
  expect(card.querySelector(".rec-poster-fallback")).not.toBeNull();
  expect(container.querySelector('img[src=""]')).toBeNull();
});
