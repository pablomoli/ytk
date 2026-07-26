import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { QueueItemViewer } from "./QueueItemViewer";

const item = {
  url: "https://www.reddit.com/r/rust/comments/abc/x/",
  source: "reddit",
  author: "someone",
  shared_at: "2026-01-06",
  text: "A post about borrow checking",
};

const noop = () => {};

test("shows the item's provenance, text and canonical url", () => {
  render(<QueueItemViewer item={item} selected={false} onToggleSelect={noop} onClose={noop} />);

  expect(screen.getByTestId("viewer-source")).toHaveTextContent("reddit");
  expect(screen.getByTestId("viewer-place")).toHaveTextContent("r/rust");
  expect(screen.getByTestId("viewer-author")).toHaveTextContent("someone");
  expect(screen.getByText("6 Jan 2026")).toBeInTheDocument();
  expect(screen.getByText("A post about borrow checking")).toBeInTheDocument();
  expect(screen.getByTestId("viewer-open")).toHaveAttribute("href", item.url);
});

/* The whole point of the surface: it reports selection but never changes it. */
test("opening the viewer does not select the item", () => {
  const onToggleSelect = vi.fn();
  render(
    <QueueItemViewer item={item} selected={false} onToggleSelect={onToggleSelect} onClose={noop} />,
  );
  expect(onToggleSelect).not.toHaveBeenCalled();
  expect(screen.getByRole("checkbox")).toHaveAttribute("aria-checked", "false");
});

test("selection is available from the viewer through an explicit control", () => {
  const onToggleSelect = vi.fn();
  render(
    <QueueItemViewer item={item} selected={false} onToggleSelect={onToggleSelect} onClose={noop} />,
  );

  fireEvent.click(screen.getByRole("checkbox"));

  expect(onToggleSelect).toHaveBeenCalledTimes(1);
});

test("reflects an already-selected item and offers to deselect", () => {
  render(<QueueItemViewer item={item} selected onToggleSelect={noop} onClose={noop} />);
  const box = screen.getByRole("checkbox");
  expect(box).toHaveAttribute("aria-checked", "true");
  expect(box).toHaveTextContent("deselect");
});

test("closes on the close button", () => {
  const onClose = vi.fn();
  render(<QueueItemViewer item={item} selected={false} onToggleSelect={noop} onClose={onClose} />);

  fireEvent.click(screen.getByRole("button", { name: "close" }));

  expect(onClose).toHaveBeenCalledTimes(1);
});

test("states plainly when there is no preview and no captured text", () => {
  render(
    <QueueItemViewer
      item={{ url: "https://example.com/a", source: "web" }}
      selected={false}
      onToggleSelect={noop}
      onClose={noop}
    />,
  );
  expect(screen.getByTestId("viewer-nopreview")).toBeInTheDocument();
  expect(screen.getByText(/no captured text/i)).toBeInTheDocument();
});

test("says there is no original to open when the url is not a link", () => {
  render(
    <QueueItemViewer
      item={{ url: "imessage:session:527ad6307d540cd9", source: "imessage", text: "hi" }}
      selected={false}
      onToggleSelect={noop}
      onClose={noop}
    />,
  );
  expect(screen.queryByTestId("viewer-open")).not.toBeInTheDocument();
  expect(screen.getByTestId("viewer-nolink")).toBeInTheDocument();
  // The identifier itself is still worth showing.
  expect(screen.getByText("imessage:session:527ad6307d540cd9")).toBeInTheDocument();
});

/* A dead preview URL must degrade to the unavailable state rather than leaving
   a broken-image box, which is the same failure the cards had. */
test("falls back to the unavailable state when the preview fails to load", () => {
  const { container } = render(
    <QueueItemViewer
      item={{ ...item, preview_url: "https://example.com/gone.jpg" }}
      selected={false}
      onToggleSelect={noop}
      onClose={noop}
    />,
  );

  fireEvent.error(container.querySelector("img")!);

  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByTestId("viewer-nopreview")).toBeInTheDocument();
});
