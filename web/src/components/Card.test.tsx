import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Card } from "./Card";

const noop = () => {};

test("renders a youtube card with title and source badge", () => {
  render(
    <Card
      item={{ url: "https://youtube.com/watch?v=1", source: "youtube", text: "Hello" }}
      onInspect={noop}
      onToggleSelect={noop}
    />,
  );
  expect(screen.getByText("Hello")).toBeInTheDocument();
  expect(screen.getByTestId("card-source")).toHaveTextContent("youtube");
});

test("renders an imessage item as a text card without an image", () => {
  render(
    <Card
      item={{ url: "u", source: "imessage", text: "note body", author: "me" }}
      onInspect={noop}
      onToggleSelect={noop}
    />,
  );
  expect(screen.getByText("note body")).toBeInTheDocument();
  expect(screen.getByText("me")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

test("renders a media card with an image sourced from /api/cover", () => {
  const { container } = render(
    <Card
      item={{ url: "u", source: "youtube", text: "Hello" }}
      onInspect={noop}
      onToggleSelect={noop}
    />,
  );
  const img = container.querySelector("img");
  expect(img).not.toBeNull();
  expect(img).toHaveAttribute("src", expect.stringContaining("/api/cover"));
});

test("applies the selected class when selected is true", () => {
  const { container } = render(
    <Card
      item={{ url: "u", source: "youtube", text: "Hello" }}
      onInspect={noop}
      onToggleSelect={noop}
      selected
    />,
  );
  expect(container.querySelector(".card")).toHaveClass("selected");
});

test("applies the ingesting class and renders a spinner when ingesting", () => {
  const { container } = render(
    <Card
      item={{ url: "u", source: "youtube", text: "Hello" }}
      onInspect={noop}
      onToggleSelect={noop}
      state="ingesting"
    />,
  );
  expect(container.querySelector(".card")).toHaveClass("ingesting");
  expect(container.querySelector(".spinner")).not.toBeNull();
});

test("applies the queued class without a selected outline", () => {
  const { container } = render(
    <Card
      item={{ url: "u", source: "youtube", text: "Hello" }}
      onInspect={noop}
      onToggleSelect={noop}
      state="queued"
    />,
  );
  expect(container.querySelector(".card")).toHaveClass("queued");
  expect(container.querySelector(".card")).not.toHaveClass("selected");
});

test("marks a profile-ranked card with a quiet theme tag and no score", () => {
  const { container } = render(
    <Card
      item={{ url: "u", source: "tiktok", text: "Shader sketch" }}
      onInspect={noop}
      onToggleSelect={noop}
      profileMatch={{
        url: "u",
        title: "Shader sketch",
        source: "tiktok",
        theme: "Creative coding",
        score: 0.731,
      }}
    />,
  );
  expect(container.querySelector(".card")).toHaveClass("profile-match");
  expect(container.querySelector(".profile-theme-tag")).toHaveTextContent("Creative coding");
  // The numeric score pill was removed; no score should render on the card.
  expect(screen.queryByText(/match 0\.\d+/)).not.toBeInTheDocument();
  expect(screen.queryByText("0.73")).not.toBeInTheDocument();
});

/* --- #123: inspection, selection and the original link are three things --- */

test("every item exposes an open-original link pointing at the canonical url", () => {
  render(
    <Card
      item={{ url: "https://www.reddit.com/r/rust/comments/abc/x/", source: "reddit" }}
      onInspect={noop}
      onToggleSelect={noop}
    />,
  );
  const link = screen.getByRole("link", { name: /open original/i });
  expect(link).toHaveAttribute("href", "https://www.reddit.com/r/rust/comments/abc/x/");
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noreferrer");
});

/* The structural half of "link activation never toggles card selection": if the
   link is not inside the inspect target, a click on it cannot bubble into the
   card's handler at all, whatever that handler happens to filter for. */
test("the link and checkbox are not nested inside the inspect target", () => {
  render(
    <Card
      item={{ url: "https://example.com/a", source: "web" }}
      onInspect={noop}
      onToggleSelect={noop}
    />,
  );
  const inspect = screen.getByRole("button", { name: /^inspect/i });
  expect(inspect).not.toContainElement(screen.getByRole("link", { name: /open original/i }));
  expect(inspect).not.toContainElement(screen.getByRole("checkbox"));
});

test("clicking the card body inspects and does not select", () => {
  const onInspect = vi.fn();
  const onToggleSelect = vi.fn();
  render(
    <Card
      item={{ url: "https://example.com/a", source: "web", text: "Hello" }}
      onInspect={onInspect}
      onToggleSelect={onToggleSelect}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /^inspect/i }));

  expect(onInspect).toHaveBeenCalledTimes(1);
  expect(onToggleSelect).not.toHaveBeenCalled();
});

test("inspects from the keyboard", () => {
  const onInspect = vi.fn();
  render(
    <Card
      item={{ url: "https://example.com/a", source: "web", text: "Hello" }}
      onInspect={onInspect}
      onToggleSelect={noop}
    />,
  );

  const inspect = screen.getByRole("button", { name: /^inspect/i });
  fireEvent.keyDown(inspect, { key: "Enter" });
  fireEvent.keyDown(inspect, { key: " " });

  expect(onInspect).toHaveBeenCalledTimes(2);
});

test("the checkbox selects and does not inspect", () => {
  const onInspect = vi.fn();
  const onToggleSelect = vi.fn();
  render(
    <Card
      item={{ url: "https://example.com/a", source: "web", text: "Hello" }}
      onInspect={onInspect}
      onToggleSelect={onToggleSelect}
    />,
  );

  const box = screen.getByRole("checkbox");
  expect(box).toHaveAttribute("aria-checked", "false");
  fireEvent.click(box);

  expect(onToggleSelect).toHaveBeenCalledTimes(1);
  expect(onInspect).not.toHaveBeenCalled();
});

test("the checkbox reports the selected state", () => {
  render(
    <Card
      item={{ url: "https://example.com/a", source: "web" }}
      onInspect={noop}
      onToggleSelect={noop}
      selected
    />,
  );
  expect(screen.getByRole("checkbox")).toHaveAttribute("aria-checked", "true");
});

/* An iMessage capture's url is a synthetic session id. Rendering a link for it
   would give 184 of the 3,603 queued rows a control that navigates nowhere. */
test("withholds the open-original link when there is no canonical url", () => {
  render(
    <Card
      item={{ url: "imessage:session:527ad6307d540cd9", source: "imessage", text: "hi", author: "me" }}
      onInspect={noop}
      onToggleSelect={noop}
    />,
  );
  expect(screen.queryByRole("link", { name: /open original/i })).not.toBeInTheDocument();
  // Selection must still be available on those items.
  expect(screen.getByRole("checkbox")).toBeInTheDocument();
});

/* A reddit item with no media used to fall back to a large tile captioned only
   "reddit". It must stay identifiable from its provenance alone. */
test("an imageless reddit item still shows its community, author and date", () => {
  const { container } = render(
    <Card
      item={{
        url: "https://www.reddit.com/r/rust/comments/abc/x/",
        source: "reddit",
        author: "someone",
        shared_at: "2026-01-06",
        text: "A post about borrow checking",
      }}
      onInspect={noop}
      onToggleSelect={noop}
    />,
  );

  fireEvent.error(container.querySelector("img")!);

  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByTestId("card-place")).toHaveTextContent("r/rust");
  expect(screen.getByTestId("card-author")).toHaveTextContent("someone");
  expect(screen.getByTestId("card-captured")).toHaveTextContent("6 Jan 2026");
  expect(screen.getByText("A post about borrow checking")).toBeInTheDocument();
  expect(screen.getByText(/no preview available/i)).toBeInTheDocument();
});
