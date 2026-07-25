import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ScrollReveal } from "./ScrollReveal";

const PROSE = "the observatory is a private instrument";

/* An element is unreadable if anything under it is left dimmed or blurred by
   inline style — the state GSAP writes and the CSS reduced-motion kill-switch
   cannot reach. */
function dimmedNodes(root: HTMLElement): HTMLElement[] {
  const nodes = [root, ...root.querySelectorAll<HTMLElement>("*")];
  return nodes.filter((node) => {
    const opacity = node.style.opacity;
    const filter = node.style.filter;
    const faded = opacity !== "" && Number.parseFloat(opacity) < 1;
    const blurred = filter !== "" && filter !== "none" && !/blur\(0(px)?\)/.test(filter);
    return faded || blurred;
  });
}

function setReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    onchange: null,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => setReducedMotion(false));

test("renders paragraph text intact", () => {
  render(<ScrollReveal>{PROSE}</ScrollReveal>);
  expect(screen.getByText(PROSE)).toBeInTheDocument();
});

test("settles fully readable when motion is allowed", async () => {
  setReducedMotion(false);
  const { container } = render(<ScrollReveal>{PROSE}</ScrollReveal>);
  const paragraph = container.querySelector("p")!;

  await waitFor(
    () => {
      expect(dimmedNodes(paragraph)).toEqual([]);
      expect(paragraph.textContent).toBe(PROSE);
    },
    { timeout: 4000 },
  );
});

test("renders plain readable prose under reduced motion", async () => {
  setReducedMotion(true);
  const { container } = render(<ScrollReveal>{PROSE}</ScrollReveal>);
  const paragraph = container.querySelector("p")!;

  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(dimmedNodes(paragraph)).toEqual([]);
  expect(paragraph.textContent).toBe(PROSE);
});

test("both motion preferences end on the same readable text", async () => {
  setReducedMotion(true);
  const reduced = render(<ScrollReveal>{PROSE}</ScrollReveal>);
  const reducedText = reduced.container.querySelector("p")!.textContent;
  reduced.unmount();

  setReducedMotion(false);
  const full = render(<ScrollReveal>{PROSE}</ScrollReveal>);
  const paragraph = full.container.querySelector("p")!;
  await waitFor(
    () => {
      expect(dimmedNodes(paragraph)).toEqual([]);
      expect(paragraph.textContent).toBe(reducedText);
    },
    { timeout: 4000 },
  );
});

test("leaves no inline dimming behind after unmount", async () => {
  setReducedMotion(false);
  const { container, unmount } = render(<ScrollReveal>{PROSE}</ScrollReveal>);
  const paragraph = container.querySelector("p")!;
  await new Promise((resolve) => setTimeout(resolve, 100));
  unmount();
  expect(dimmedNodes(paragraph)).toEqual([]);
});
