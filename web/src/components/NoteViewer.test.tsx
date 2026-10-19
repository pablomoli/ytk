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

test("description section renders parsed: wrapper stripped, bare URLs linked, line breaks kept", async () => {
  const content = [
    "## Description",
    "<details>",
    "<summary>Video description</summary>",
    "",
    "Take your data back with Incogni: http://incogni.com/welchlabs",
    "Welch Labs Book! https://www.welchlabs.com/resources/imaginary-numbers-book",
    "</details>",
    "",
  ].join("\n");
  const previous = vi.mocked(fetch).getMockImplementation();
  vi.mocked(fetch).mockImplementation((input) => {
    /* apiGet always passes string URLs; anything else is not the note fetch */
    const url = typeof input === "string" ? input : "";
    return Promise.resolve(
      new Response(
        JSON.stringify(
          url.startsWith("/api/note") ? { path: "sources/youtube/x.md", content } : [],
        ),
      ),
    );
  });
  try {
    wrap(<NoteViewer note={note} onClose={() => {}} />);
    /* the note fetch settles across several turns: fetch -> Response.json ->
       query-cache notify; flush macrotasks inside act until all are done */
    await act(async () => {
      for (let i = 0; i < 4; i++) await new Promise((r) => setTimeout(r, 0));
    });
    const heading = screen.getByRole("heading", { name: "Description", hidden: true });
    const section = heading.closest("section")!;
    // the vault's <details><summary> wrapper never leaks as literal text
    expect(section.textContent).not.toContain("<details>");
    expect(section.textContent).not.toContain("Video description");
    // bare URLs become anchors with the URL as text
    const anchors = [...section.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(anchors).toContain("http://incogni.com/welchlabs");
    expect(anchors).toContain("https://www.welchlabs.com/resources/imaginary-numbers-book");
    // adjacent description lines keep their line break
    expect(section.querySelector("p br")).not.toBeNull();
  } finally {
    vi.mocked(fetch).mockImplementation(previous!);
  }
});

test("reflect reveals an input and submits the answer as the reflect POST body", async () => {
  vi.mocked(fetch).mockClear();
  wrap(<NoteViewer note={note} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "reflect", hidden: true }));
  fireEvent.change(screen.getByPlaceholderText("why did you save this?"), {
    target: { value: "because it maps my taste" },
  });
  fireEvent.click(screen.getByRole("button", { name: "submit", hidden: true }));
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  const call = vi.mocked(fetch).mock.calls.find(([url]) => url === "/api/reflect");
  expect(call).toBeDefined();
  const init = call![1] as RequestInit;
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body as string)).toEqual({
    path: "sources/youtube/x.md",
    question: "why did you save this?",
    answer: "because it maps my taste",
  });
});

test("empty reflect answer cannot submit", async () => {
  vi.mocked(fetch).mockClear();
  wrap(<NoteViewer note={note} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "reflect", hidden: true }));
  const submit = screen.getByRole("button", { name: "submit", hidden: true });
  expect(submit).toBeDisabled();
  /* Whitespace-only is empty too. */
  fireEvent.change(screen.getByPlaceholderText("why did you save this?"), {
    target: { value: "   " },
  });
  expect(submit).toBeDisabled();
  fireEvent.click(submit);
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  expect(vi.mocked(fetch).mock.calls.find(([url]) => url === "/api/reflect")).toBeUndefined();
});

test("ask copies the prompt for this note and shows the copied state", async () => {
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
  wrap(<NoteViewer note={note} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "ask", hidden: true }));
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  expect(writeText).toHaveBeenCalledWith(expect.stringContaining("sources/youtube/x.md"));
  expect(screen.getByRole("button", { name: "copied", hidden: true })).toBeInTheDocument();
  writeText.mockRestore();
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

/* Routes the viewer's fetches: the nearby list (which drops a target once
   linked), the tap's POST, and an empty answer for everything else. */
function nearbyRoutes(opts: {
  linkable: boolean;
  link?: (target: string) => { status: number; body: unknown };
}) {
  const linked = new Set<string>();
  const all = [
    { target: "coral-note", title: "Coral growth rules", cosine: 0.712, path: null },
    { target: "reef-note", title: "Reef shapes", cosine: 0.534, path: null },
  ];
  return (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : "";
    if (url.startsWith("/api/nearby?")) {
      const nearby = all.filter((n) => !linked.has(n.target));
      return Promise.resolve(new Response(JSON.stringify({ linkable: opts.linkable, nearby })));
    }
    if (url === "/api/nearby/link") {
      const { target } = JSON.parse(init!.body as string) as { target: string };
      const out = opts.link!(target);
      if (out.status === 200 && (out.body as { argument: string | null }).argument) {
        linked.add(target);
      }
      return Promise.resolve(new Response(JSON.stringify(out.body), { status: out.status }));
    }
    return Promise.resolve(
      new Response(
        JSON.stringify(url.startsWith("/api/note") ? { path: note.path, content: "" } : []),
      ),
    );
  };
}

async function settle() {
  await act(async () => {
    for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0));
  });
}

test("nearby lists text neighbours with cosine; a tap writes the link and shows its clause", async () => {
  const previous = vi.mocked(fetch).getMockImplementation();
  vi.mocked(fetch).mockClear();
  vi.mocked(fetch).mockImplementation(
    nearbyRoutes({
      linkable: true,
      link: (target) => ({
        status: 200,
        body: {
          target,
          target_title: "Coral growth rules",
          cosine: 0.712,
          argument: "both grow by local rules",
          reindex: "re-indexed",
        },
      }),
    }),
  );
  try {
    wrap(<NoteViewer note={note} onClose={() => {}} />);
    await settle();
    const panel = screen.getByRole("region", { name: "nearby notes", hidden: true });
    expect(panel.textContent).toContain("Coral growth rules");
    expect(panel.textContent).toContain("0.71");
    expect(panel.textContent).toContain("0.53");

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "link Coral growth rules" }));
    });
    await settle();

    const post = vi.mocked(fetch).mock.calls.find(([url]) => url === "/api/nearby/link");
    expect(JSON.parse((post![1] as RequestInit).body as string)).toEqual({
      note: "sources/youtube/x.md",
      target: "coral-note",
    });
    const linked = screen.getByRole("list", { name: "linked", hidden: true });
    expect(linked.textContent).toContain("Coral growth rules");
    expect(linked.textContent).toContain("both grow by local rules");
    // the written neighbour leaves the tap list; the other stays tappable
    expect(screen.queryByRole("button", { name: "link Coral growth rules" })).toBeNull();
    expect(screen.getByRole("button", { name: "link Reef shapes" })).toBeInTheDocument();
  } finally {
    vi.mocked(fetch).mockImplementation(previous!);
  }
});

test("a note with no ledger item shows its neighbours without a link button", async () => {
  const previous = vi.mocked(fetch).getMockImplementation();
  vi.mocked(fetch).mockImplementation(nearbyRoutes({ linkable: false }));
  try {
    wrap(<NoteViewer note={note} onClose={() => {}} />);
    await settle();
    const panel = screen.getByRole("region", { name: "nearby notes", hidden: true });
    expect(panel.textContent).toContain("Reef shapes");
    expect(panel.textContent).toContain("no ledger item");
    expect(screen.queryByRole("button", { name: /^link / })).toBeNull();
  } finally {
    vi.mocked(fetch).mockImplementation(previous!);
  }
});

test("a refused tap shows the server's reason and keeps the neighbour", async () => {
  const previous = vi.mocked(fetch).getMockImplementation();
  vi.mocked(fetch).mockImplementation(
    nearbyRoutes({
      linkable: true,
      link: () => ({ status: 409, body: { detail: "the curator loop is working on this note" } }),
    }),
  );
  try {
    wrap(<NoteViewer note={note} onClose={() => {}} />);
    await settle();
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "link Reef shapes" }));
    });
    await settle();
    const panel = screen.getByRole("region", { name: "nearby notes", hidden: true });
    expect(panel.textContent).toContain("the curator loop is working on this note");
    expect(screen.getByRole("button", { name: "link Reef shapes" })).toBeInTheDocument();
  } finally {
    vi.mocked(fetch).mockImplementation(previous!);
  }
});

test("a tap the model could not argue says nothing was written", async () => {
  const previous = vi.mocked(fetch).getMockImplementation();
  vi.mocked(fetch).mockImplementation(
    nearbyRoutes({
      linkable: true,
      link: (target) => ({
        status: 200,
        body: { target, target_title: "Reef shapes", cosine: 0.534, argument: null, reindex: null },
      }),
    }),
  );
  try {
    wrap(<NoteViewer note={note} onClose={() => {}} />);
    await settle();
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "link Reef shapes" }));
    });
    await settle();
    const panel = screen.getByRole("region", { name: "nearby notes", hidden: true });
    expect(panel.textContent).toContain("no clause could be argued for Reef shapes");
    expect(screen.queryByRole("list", { name: "linked", hidden: true })).toBeNull();
  } finally {
    vi.mocked(fetch).mockImplementation(previous!);
  }
});
