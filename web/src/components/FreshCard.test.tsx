import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { FreshCard } from "./FreshCard";

const note = {
  path: "sources/video.md",
  stem: "video",
  title: "A video",
  url: "https://example.com/video",
  source: "youtube",
  added: "2026-07-10",
  thumbnail: "images/video.jpg",
  tags: ["reference"],
  has_take: true,
};

test("uses vault media for fresh-note thumbnails", () => {
  const { container } = render(<FreshCard note={note} onOpen={() => {}} onDelete={() => {}} />);

  expect(container.querySelector("img")).toHaveAttribute("src", "/vault-media/images/video.jpg");
  expect(screen.getByText("#reference")).toBeInTheDocument();
});

test("opens through its button and keeps external links separate", () => {
  const onOpen = vi.fn();
  render(<FreshCard note={note} onOpen={onOpen} onDelete={() => {}} />);

  fireEvent.click(screen.getByRole("button", { name: "open note" }));
  fireEvent.click(screen.getByRole("link", { name: "open" }));

  expect(onOpen).toHaveBeenCalledTimes(1);
});

test("ask copies the prompt, flips its label, and never opens the card", async () => {
  const onOpen = vi.fn();
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  const { container } = render(<FreshCard note={note} onOpen={onOpen} onDelete={() => {}} />);

  fireEvent.click(container.firstElementChild!); // card background opens
  fireEvent.click(screen.getByRole("button", { name: "ask" }));
  await screen.findByRole("button", { name: "copied" });

  expect(writeText).toHaveBeenCalledWith("tell me something about sources/video.md");
  expect(onOpen).toHaveBeenCalledTimes(1);
  writeText.mockRestore();
});

test("reflect input submits the right reflect POST body", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify({ status: "accepted" })))),
  );
  render(<FreshCard note={note} onOpen={() => {}} onDelete={() => {}} />);

  fireEvent.click(screen.getByRole("button", { name: "reflect" }));
  fireEvent.change(screen.getByPlaceholderText("why did you save this?"), {
    target: { value: "it maps my taste" },
  });
  fireEvent.click(screen.getByRole("button", { name: "submit" }));
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });

  const call = vi.mocked(fetch).mock.calls.find(([url]) => url === "/api/reflect");
  expect(call).toBeDefined();
  const init = call![1] as RequestInit;
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body as string)).toEqual({
    path: "sources/video.md",
    question: "why did you save this?",
    answer: "it maps my taste",
  });
  /* Accepted: the input closes and the button flips to a quiet reflecting label. */
  expect(screen.queryByPlaceholderText("why did you save this?")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "reflecting" })).toBeInTheDocument();
  vi.unstubAllGlobals();
});

test("empty reflect answer cannot submit", async () => {
  vi.stubGlobal("fetch", vi.fn());
  render(<FreshCard note={note} onOpen={() => {}} onDelete={() => {}} />);

  fireEvent.click(screen.getByRole("button", { name: "reflect" }));
  const submit = screen.getByRole("button", { name: "submit" });
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByPlaceholderText("why did you save this?"), {
    target: { value: "   " },
  });
  expect(submit).toBeDisabled();
  fireEvent.click(submit);
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });

  expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
});

test("opening the reflect input never opens the card", () => {
  const onOpen = vi.fn();
  render(<FreshCard note={note} onOpen={onOpen} onDelete={() => {}} />);

  fireEvent.click(screen.getByRole("button", { name: "reflect" }));
  fireEvent.click(screen.getByPlaceholderText("why did you save this?"));

  expect(onOpen).not.toHaveBeenCalled();
});

test("renders memos as text cards without a vault image", () => {
  render(
    <FreshCard
      note={{
        ...note,
        source: "memo",
        preview: "A captured thought",
        thumbnail: null,
        kind: "thought",
      }}
      onOpen={() => {}}
      onDelete={() => {}}
    />,
  );

  expect(screen.getByText("A captured thought")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

test("thumbnail dissolve mounts after image load", () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
  const { container } = render(
    <FreshCard note={{ ...note, thumbnail: "t.jpg" }} onOpen={() => {}} onDelete={() => {}} />,
  );
  expect(container.querySelector(".pixel-dissolve")).not.toBeInTheDocument();
  fireEvent.load(container.querySelector("img")!);
  expect(container.querySelector(".pixel-dissolve")).toBeInTheDocument();
  vi.unstubAllGlobals();
});
