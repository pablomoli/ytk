import { render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MasonryGrid } from "./MasonryGrid";

/* Held on a plain object so the assertions never reference GSAP's own static
   methods, which the unbound-method rule rejects. */
const flip = vi.hoisted(() => ({
  getState: vi.fn((targets: HTMLElement[]) => ({ mock: "state", targets })),
  from: vi.fn(),
}));

vi.mock("../lib/motion", () => ({
  DUR: { base: 0.18 },
  HOUSE_EASE: "house",
  reducedMotion: () => false,
  Flip: flip,
}));

/* jsdom reports clientWidth 0, which makes relayout bail before it writes any
   styles, and never schedules a real frame. Both stubs must be in place before
   the effect runs its first layout pass. */
function stubLayoutEnvironment(width = 802) {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    cb(0);
    return 1;
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    value: width,
  });
}

afterEach(() => {
  Reflect.deleteProperty(HTMLElement.prototype, "clientWidth");
  vi.unstubAllGlobals();
  flip.from.mockClear();
  flip.getState.mockClear();
});

function cards(ids: string[]) {
  return ids.map((id) => (
    <div className="card" key={id}>
      {id}
    </div>
  ));
}

test("writes absolute inline positioning onto every child", () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    cb(0);
    return 1;
  });
  // jsdom reports clientWidth 0, which makes relayout bail before it writes
  // any styles. Stub it on the prototype so it's in place before the effect
  // runs its first (synchronous, via the stubbed rAF) layout pass.
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    value: 802,
  });

  const { container } = render(
    <MasonryGrid>
      <div className="card">a</div>
      <div className="card">b</div>
      <div className="skel" />
    </MasonryGrid>,
  );

  const grid = container.querySelector(".masonry") as HTMLElement;
  expect(grid.style.height).toMatch(/px$/);
  for (const el of grid.children) {
    const style = (el as HTMLElement).style;
    expect(style.position).toBe("absolute");
    expect(style.left).toMatch(/px$/);
    expect(style.top).toMatch(/px$/);
    expect(style.width).toMatch(/px$/);
  }

  Reflect.deleteProperty(HTMLElement.prototype, "clientWidth");
  vi.unstubAllGlobals();
});

/* #22. The grid used to key its layout effect on `children`, which is a fresh
   array identity on every parent render. A selection toggle, a poll, or the
   inbox's 1s elapsed clock therefore re-packed and re-tweened the whole grid
   although not one card had changed. These pin the trigger to real structural
   change. */
test("a parent re-render with the same cards does not animate", () => {
  stubLayoutEnvironment();
  const { rerender } = render(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);
  flip.from.mockClear();

  rerender(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);

  expect(flip.from).not.toHaveBeenCalled();
});

test("re-rendering many times over never accumulates animations", () => {
  stubLayoutEnvironment();
  const { rerender } = render(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);
  flip.from.mockClear();

  // Stands in for a running ingest job: the elapsed clock ticks, the route
  // re-renders, the cards are identical every time.
  for (let i = 0; i < 10; i++) {
    rerender(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);
  }

  expect(flip.from).not.toHaveBeenCalled();
});

test("adding a card animates the reflow", () => {
  stubLayoutEnvironment();
  const { rerender } = render(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);
  flip.from.mockClear();

  rerender(<MasonryGrid>{cards(["a", "b", "c", "d"])}</MasonryGrid>);

  expect(flip.from).toHaveBeenCalledTimes(1);
});

test("reordering the same cards animates the reflow", () => {
  stubLayoutEnvironment();
  const { rerender } = render(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);
  flip.from.mockClear();

  // Same membership, different order — what a profile re-rank produces.
  rerender(<MasonryGrid>{cards(["c", "a", "b"])}</MasonryGrid>);

  expect(flip.from).toHaveBeenCalledTimes(1);
});

test("appending a page animates only the cards that were already placed", () => {
  stubLayoutEnvironment();
  const first = ["a", "b", "c"];
  const { rerender } = render(<MasonryGrid>{cards(first)}</MasonryGrid>);
  flip.getState.mockClear();

  // Pagination: the next page arrives while the current one stays put.
  rerender(<MasonryGrid>{cards([...first, "d", "e", "f"])}</MasonryGrid>);

  // The brand-new cards are still in static flow. Handing them to Flip is
  // what dragged them across the document on every page append.
  const captured = flip.getState.mock.calls[0]?.[0];
  expect(captured).toBeDefined();
  expect(captured).toHaveLength(first.length);
  for (const el of captured ?? []) {
    expect(el.style.top).not.toBe("");
  }
});

test("the very first layout animates nothing", () => {
  stubLayoutEnvironment();
  render(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);

  expect(flip.from).not.toHaveBeenCalled();
});

test("every card still gets placed after a no-op re-render", () => {
  stubLayoutEnvironment();
  const { container, rerender } = render(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);
  rerender(<MasonryGrid>{cards(["a", "b", "c"])}</MasonryGrid>);

  const grid = container.querySelector(".masonry") as HTMLElement;
  expect(grid.style.height).toMatch(/px$/);
  for (const el of grid.children) {
    expect((el as HTMLElement).style.top).toMatch(/px$/);
  }
});
