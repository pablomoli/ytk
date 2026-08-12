import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { renderInline } from "./inlineMarkdown";

test("bold text renders a strong element", () => {
  const { container } = render(<>{renderInline("**x**")}</>);
  const strong = container.querySelector("strong");
  expect(strong).not.toBeNull();
  expect(strong?.textContent).toBe("x");
});

test("markdown link renders an anchor with href and text", () => {
  const { container } = render(<>{renderInline("[a](http://b)")}</>);
  const anchor = container.querySelector("a");
  expect(anchor).not.toBeNull();
  expect(anchor?.getAttribute("href")).toBe("http://b");
  expect(anchor?.textContent).toBe("a");
  expect(anchor?.getAttribute("target")).toBe("_blank");
  expect(anchor?.getAttribute("rel")).toBe("noreferrer");
});

test("italic text renders an em element", () => {
  const { container } = render(<>{renderInline("from the *current* model")}</>);
  const em = container.querySelector("em");
  expect(em?.textContent).toBe("current");
  expect(container.textContent).toBe("from the current model");
});

test("double-star bold is not mangled by the italic branch", () => {
  const { container } = render(<>{renderInline("**bold** not *italic* mixed")}</>);
  expect(container.querySelector("strong")?.textContent).toBe("bold");
  expect(container.querySelector("em")?.textContent).toBe("italic");
});

test("snake_case identifiers are left untouched (no underscore italic)", () => {
  const { container } = render(<>{renderInline("call depth_anything_v3 now")}</>);
  expect(container.querySelector("em")).toBeNull();
  expect(container.textContent).toBe("call depth_anything_v3 now");
});

test("plain text passes through unchanged", () => {
  const { container } = render(<>{renderInline("just plain text")}</>);
  expect(container.textContent).toBe("just plain text");
  expect(container.querySelector("strong")).toBeNull();
  expect(container.querySelector("a")).toBeNull();
});

test("a bare URL autolinks with the URL itself as the text", () => {
  const { container } = render(
    <>{renderInline("patrons at https://www.patreon.com/welchlabs today")}</>,
  );
  const anchor = container.querySelector("a");
  expect(anchor?.getAttribute("href")).toBe("https://www.patreon.com/welchlabs");
  expect(anchor?.textContent).toBe("https://www.patreon.com/welchlabs");
  expect(anchor?.getAttribute("target")).toBe("_blank");
  expect(container.textContent).toBe("patrons at https://www.patreon.com/welchlabs today");
});

test("trailing punctuation stays out of a bare URL", () => {
  const { container } = render(
    <>{renderInline("see https://neuralblog.github.io/logit-prisms/, then this")}</>,
  );
  expect(container.querySelector("a")?.getAttribute("href")).toBe(
    "https://neuralblog.github.io/logit-prisms/",
  );
  expect(container.textContent).toBe("see https://neuralblog.github.io/logit-prisms/, then this");
});

test("a markdown link's URL is not linked twice by the bare-URL branch", () => {
  const { container } = render(<>{renderInline("[label](https://x.com) and more")}</>);
  const anchors = container.querySelectorAll("a");
  expect(anchors).toHaveLength(1);
  expect(anchors[0].textContent).toBe("label");
});

test("a line mixing bold and a link renders both", () => {
  const { container } = render(<>{renderInline("see **this** and [link](https://x.com)")}</>);
  const strong = container.querySelector("strong");
  const anchor = container.querySelector("a");
  expect(strong?.textContent).toBe("this");
  expect(anchor?.textContent).toBe("link");
  expect(anchor?.getAttribute("href")).toBe("https://x.com");
  expect(container.textContent).toBe("see this and link");
});
