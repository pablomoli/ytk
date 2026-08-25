import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { page } from "vitest/browser";
import { afterEach, expect, test, vi } from "vitest";
import { userEvent } from "vite-plus/test/browser";

const router = vi.hoisted(() => ({ pathname: "/" }));

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    to,
    children,
    activeProps: _activeProps,
    activeOptions: _activeOptions,
    ...props
  }: React.ComponentProps<"a"> & {
    to: string;
    activeProps?: unknown;
    activeOptions?: unknown;
  }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useLocation: () => ({ pathname: router.pathname }),
}));

import { HUB_DESTINATIONS, HubNav } from "./HubNav";

afterEach(() => {
  router.pathname = "/";
});

test("keeps four core destinations primary and every secondary route in More", () => {
  render(<HubNav />);
  const nav = screen.getByRole("navigation", { name: "Hub navigation" });
  expect(within(nav).getAllByRole("link").map((link) => link.textContent)).toEqual([
    "Fresh",
    "Inbox",
    "Library",
    "Map",
  ]);
  expect(within(nav).queryByRole("link", { name: "Tag cleanup" })).toBeNull();

  fireEvent.click(within(nav).getByRole("button", { name: "More" }));
  expect(screen.getByRole("link", { name: "Tag cleanup" })).toHaveAttribute("href", "/tags");
  expect(screen.getByText("Learn and curate")).toBeInTheDocument();
  expect(screen.getByText("Labs")).toBeInTheDocument();
  expect(screen.getByText("Maintain")).toBeInTheDocument();
});

test("the registry preserves every existing deep link exactly once", () => {
  expect(HUB_DESTINATIONS.map((item) => item.to)).toEqual([
    "/",
    "/inbox",
    "/library",
    "/map",
    "/recs",
    "/channels",
    "/profile",
    "/orb",
    "/galaxy",
    "/atlas",
    "/garden",
    "/growth",
    "/lsd",
    "/docs",
    "/tags",
    "/settings",
  ]);
  expect(new Set(HUB_DESTINATIONS.map((item) => item.to)).size).toBe(16);
});

test("More announces when a nested destination is current", () => {
  router.pathname = "/atlas";
  render(<HubNav />);
  expect(screen.getByRole("button", { name: "More, current section" })).toHaveAttribute(
    "data-active",
    "true",
  );
});

test("Escape closes More and restores focus", async () => {
  render(<HubNav />);
  const trigger = screen.getByRole("button", { name: "More" });
  trigger.focus();
  fireEvent.click(trigger);
  expect(screen.getByRole("link", { name: "Atlas" })).toBeInTheDocument();
  await act(async () => userEvent.keyboard("{Escape}"));
  await waitFor(() => expect(screen.queryByRole("link", { name: "Atlas" })).toBeNull());
  expect(trigger).toHaveFocus();
});

test.each([
  [375, 812],
  [768, 1024],
  [1440, 900],
])("navigation stays within a %ix%i viewport", async (width, height) => {
  await page.viewport(width, height);
  render(<HubNav />);
  const nav = screen.getByRole("navigation", { name: "Hub navigation" });
  expect(nav.getBoundingClientRect().right).toBeLessThanOrEqual(width);
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width);
});
