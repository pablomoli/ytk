import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { SOURCES, canonicalSource, sourceIcon, sourceIconKey } from "./icons";

/* The source filter is icon-only and reveals the name on hover (#126), so two
   sources sharing a glyph are two cells a reader cannot tell apart. reddit and
   imessage both used to resolve to the web globe. */
test("every filterable source has its own glyph", () => {
  const keys = SOURCES.map(sourceIconKey);
  expect(new Set(keys).size).toBe(SOURCES.length);
});

test("no filterable source falls back to the web glyph except web itself", () => {
  const fellBack = SOURCES.filter((s) => s !== "web" && sourceIconKey(s) === "web");
  expect(fellBack).toEqual([]);
});

test("aliases still resolve to their canonical glyph", () => {
  expect(sourceIconKey("instagram-reel")).toBe("instagram");
  expect(canonicalSource("instagram-reel")).toBe("instagram");
});

/* An unknown source is not an error — it is a new capture type that has not
   been given a glyph yet, and the globe is the honest placeholder. */
test("an unknown source falls back to the web glyph", () => {
  expect(sourceIconKey("carrier-pigeon")).toBe("web");
});

test("renders an svg with a path and honours the requested size", () => {
  const { container } = render(<>{sourceIcon("reddit", 22)}</>);
  const svg = container.querySelector("svg");
  expect(svg).toHaveAttribute("width", "22");
  expect(svg).toHaveAttribute("aria-hidden", "true");
  expect(svg?.querySelector("path")).not.toBeNull();
});

test("defaults to the 16px size used in card meta rows", () => {
  const { container } = render(<>{sourceIcon("youtube")}</>);
  expect(container.querySelector("svg")).toHaveAttribute("width", "16");
});
