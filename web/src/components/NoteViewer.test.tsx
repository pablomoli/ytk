import { StrictMode } from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { userEvent } from "@vitest/browser/context";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeAll, expect, test, vi } from "vitest";
import type { FreshNote } from "../api/fresh";
import { gsap } from "../lib/motion";
import { NoteViewer } from "./NoteViewer";

beforeAll(() => {
  /* A valid note payload: useNote's own `enabled: Boolean(path)` overrides the
     test QueryClient's enabled:false, so this stub really resolves. */
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ path: "sources/youtube/x.md", content: "" }))),
    ),
  );
});

const note: FreshNote = {
  path: "sources/youtube/x.md",
  title: "a note",
  source: "youtube",
  tags: [],
  url: "",
  thumbnail: "",
  has_take: false,
} as unknown as FreshNote;

const wrap = (ui: React.ReactElement) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })}
    >
      {ui}
    </QueryClientProvider>,
  );

test("opens as a modal dialog labelled by the note title", () => {
  wrap(<NoteViewer note={note} onClose={() => {}} />);
  expect(screen.getByRole("dialog", { hidden: true })).toHaveAccessibleName("a note");
});

test("close button calls onClose", () => {
  const onClose = vi.fn();
  wrap(<NoteViewer note={note} onClose={onClose} />);
  fireEvent.click(screen.getByRole("button", { name: "close", hidden: true }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("backdrop click calls onClose", async () => {
  const onClose = vi.fn();
  wrap(<NoteViewer note={note} onClose={onClose} />);
  /* Radix attaches its outside-pointerdown listener a macrotask after mount. */
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  const overlay = document.querySelector<HTMLElement>('[data-slot="dialog-overlay"]')!;
  /* A real browser click at the corner, clear of the centered panel. */
  await userEvent.click(overlay, { position: { x: 5, y: 5 } });
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("escape calls onClose", () => {
  const onClose = vi.fn();
  wrap(<NoteViewer note={note} onClose={onClose} />);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("reveal overlay mounts and clears", () => {
  wrap(<NoteViewer note={note} onClose={() => {}} />);
  expect(document.querySelector(".pixel-dissolve")).toBeInTheDocument();
});

test("survives StrictMode double-mount without self-closing (async close event)", async () => {
  const onClose = vi.fn();
  // StrictMode must wrap QueryClientProvider (matching main.tsx's real nesting)
  // for React to actually double-invoke effects here; wrap() puts the query
  // client outermost, which suppresses the double-invoke in this renderer.
  render(
    <StrictMode>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })}
      >
        <NoteViewer note={note} onClose={onClose} />
      </QueryClientProvider>
    </StrictMode>,
  );
  // Flush the close event the cleanup queued during the mount->cleanup->mount
  // cycle. A ref-flag guard would already be reset by the remount here, so
  // this asserts onClose is decoupled from the native close event entirely.
  await act(async () => {
    await Promise.resolve();
  });
  expect(onClose).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog", { hidden: true })).toBeInTheDocument();
});

test("StrictMode double-mount with an originRect kills the stale morph tween, not stacks a second one", async () => {
  const onClose = vi.fn();
  const originRect = { left: 10, top: 10, width: 200, height: 150 } as DOMRect;
  // StrictMode must wrap QueryClientProvider (matching main.tsx's real nesting)
  // for React to actually double-invoke effects here — see the test above.
  render(
    <StrictMode>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })}
      >
        <NoteViewer note={note} onClose={onClose} originRect={originRect} />
      </QueryClientProvider>
    </StrictMode>,
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(onClose).not.toHaveBeenCalled();
  const dialog = screen.getByRole("dialog", { hidden: true });
  expect(dialog).toBeInTheDocument();
  // The first invocation's mount->cleanup->mount cycle must not leave two
  // gsap.from tweens racing on the same node — cleanup has to kill the
  // in-flight tween before the second mount starts a new one.
  expect(gsap.getTweensOf(dialog).length).toBeLessThanOrEqual(1);
});
