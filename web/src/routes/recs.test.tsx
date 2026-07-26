import { render, screen, fireEvent } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
}));
vi.mock("../components/HubControls", () => ({
  HubControls: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mutate = vi.fn();
// Type-only import: the runtime module is mocked below, the type erases.
type RecCard = import("../api/recs").RecCard;
const recs: RecCard[] = [
  {
    key: "tmdb:movie:438631",
    kind: "movie",
    title: "Dune",
    year: 2021,
    creator: "Denis Villeneuve",
    poster: "https://example.com/dune.jpg",
    rating: 8.1,
    genres: ["Science Fiction", "Adventure"],
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
    genres: ["Drama"],
    overview: null,
    external_url: null,
    count: 3,
    sources: [],
    status: "want",
  },
  {
    key: "tmdb:movie:603",
    kind: "movie",
    title: "The Matrix",
    year: 1999,
    creator: "Lana Wachowski",
    poster: null,
    rating: null,
    genres: ["Science Fiction"],
    overview: null,
    external_url: null,
    count: 1,
    sources: [],
    status: "seen",
  },
  {
    key: "hardcover:book:42",
    kind: "book",
    title: "Dune (novel)",
    year: 1965,
    creator: "Frank Herbert",
    poster: null,
    rating: 9.0,
    genres: null,
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
  const Page = (Route as unknown as { options: { component: React.ComponentType } }).options
    .component;
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

function shelfNames(container: HTMLElement): string[] {
  return [...container.querySelectorAll<HTMLElement>(".shelf-name")].map(
    (h) => h.textContent ?? "",
  );
}

test("titles shelve under their primary genre; wanted titles pin to my list", () => {
  const { container } = renderPage();
  const names = shelfNames(container);
  expect(names[0]).toBe("my list"); // Breaking Bad (want) pins first
  expect(names).toContain("Science Fiction"); // Dune's genres[0]
  const myList = container.querySelector(".shelf")!;
  expect(myList.textContent).toContain("Breaking Bad");
});

test("seen and skipped titles hide until the toggle reveals them", () => {
  const { container } = renderPage();
  expect(cardByTitle(container, "The Matrix")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /seen & skipped/i }));
  expect(cardByTitle(container, "The Matrix")).not.toBeNull();
});

test("the specific genre wins the shelf over broad catch-alls", async () => {
  // Aliens arrives from TMDb as [Action, Thriller, Science Fiction]; the
  // Blockbuster rule shelves it under science fiction, not action.
  recs.push({
    key: "tmdb:movie:679",
    kind: "movie",
    title: "Aliens",
    year: 1986,
    creator: "James Cameron",
    poster: null,
    rating: null,
    genres: ["Action", "Thriller", "Science Fiction"],
    overview: null,
    external_url: null,
    count: 1,
    sources: [],
    status: null,
  });
  try {
    const { container } = renderPage();
    const shelves = [...container.querySelectorAll<HTMLElement>(".shelf")];
    const sf = shelves.find((s) => s.querySelector(".shelf-name")?.textContent === "Science Fiction");
    expect(sf?.textContent).toContain("Aliens");
    const action = shelves.find((s) => s.querySelector(".shelf-name")?.textContent === "Action");
    expect(action).toBeUndefined();
  } finally {
    recs.pop();
  }
});

test("a title without genres lands on the uncategorized shelf", () => {
  const { container } = renderPage();
  fireEvent.click(screen.getByRole("tab", { name: /read/i }));
  const names = shelfNames(container);
  expect(names).toContain("uncategorized"); // Dune (novel) has genres: null
});
