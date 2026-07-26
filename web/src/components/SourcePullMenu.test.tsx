import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { SourcePullMenu, anchorFor } from "./SourcePullMenu";
import { PULL_SOURCES } from "./icons";

const VIEW = { width: 1440, height: 800 };

test("opens below the caret when there is room", () => {
  const a = anchorFor({ left: 400, right: 460, top: 100, bottom: 134 }, 291, VIEW);
  expect(a.flipped).toBe(false);
  expect(a.top).toBe(140);
});

/* The exact geometry of the bug this replaces: the caret sat 439px down the
   rail and the menu is 291px tall. It fits below in the VIEWPORT — 327px of
   room against 297 needed — and still had its confirm button 94px out of reach,
   because .rail-scroll ended at 665 and clipped it. So the fix is escaping the
   clip, and no flip is wanted here: flipping a menu that fits would be its own
   jarring bug. */
test("does not flip when the menu fits below in the viewport", () => {
  const a = anchorFor({ left: 400, right: 460, top: 439, bottom: 473 }, 291, VIEW);
  expect(a.flipped).toBe(false);
  expect(a.top).toBe(479);
  expect(a.top + 291).toBeLessThanOrEqual(VIEW.height);
});

/* The flip is the secondary guard, for a caret genuinely near the bottom. */
test("flips above the caret when there is no room below", () => {
  const caret = { left: 400, right: 460, top: 700, bottom: 734 };
  const a = anchorFor(caret, 291, VIEW);
  expect(a.flipped).toBe(true);
  expect(a.top).toBe(700 - 291 - 6);
  expect(a.top).toBeGreaterThanOrEqual(0);
  expect(a.top + 291).toBeLessThanOrEqual(VIEW.height);
});

test("never places the menu off the top of the screen", () => {
  const a = anchorFor({ left: 400, right: 460, top: 20, bottom: 54 }, 600, { width: 1440, height: 300 });
  expect(a.top).toBeGreaterThanOrEqual(0);
});

test("keeps the menu inside the left and right edges", () => {
  const nearRight = anchorFor({ left: 1400, right: 1435, top: 10, bottom: 44 }, 100, VIEW);
  expect(nearRight.left + 200).toBeLessThanOrEqual(VIEW.width);

  const nearLeft = anchorFor({ left: 2, right: 30, top: 10, bottom: 44 }, 100, VIEW);
  expect(nearLeft.left).toBeGreaterThanOrEqual(0);
});

test("lists every pullable source once opened", () => {
  render(<SourcePullMenu onPull={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "pull specific sources" }));

  for (const s of PULL_SOURCES) {
    expect(screen.getByRole("checkbox", { name: s })).toBeInTheDocument();
  }
});

/* The whole point of the feature: fetch from one named source on demand. */
test("pulls only the chosen sources", () => {
  const onPull = vi.fn();
  render(<SourcePullMenu onPull={onPull} />);
  fireEvent.click(screen.getByRole("button", { name: "pull specific sources" }));

  fireEvent.click(screen.getByRole("checkbox", { name: "instagram" }));
  fireEvent.click(within(screen.getByRole("menu")).getByRole("button", { name: /^pull/ }));

  expect(onPull).toHaveBeenCalledWith(["instagram"]);
});

test("the confirm button is inert until something is chosen", () => {
  render(<SourcePullMenu onPull={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "pull specific sources" }));
  expect(within(screen.getByRole("menu")).getByRole("button", { name: /^pull/ })).toBeDisabled();
});

/* The menu is portaled out of the trigger's subtree, so the outside-click
   handler has to know about it — otherwise clicking a source inside the menu
   reads as an outside click and closes it before anything can be chosen. */
test("clicking inside the portaled menu does not dismiss it", () => {
  render(<SourcePullMenu onPull={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "pull specific sources" }));

  const box = screen.getByRole("checkbox", { name: "youtube" });
  fireEvent.mouseDown(box);
  fireEvent.click(box);

  expect(screen.getByRole("menu")).toBeInTheDocument();
  expect(box).toBeChecked();
});

test("closes on an outside click and on Escape", () => {
  render(<SourcePullMenu onPull={() => {}} />);
  const caret = screen.getByRole("button", { name: "pull specific sources" });

  fireEvent.click(caret);
  fireEvent.mouseDown(document.body);
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();

  fireEvent.click(caret);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

test("renders outside the rail so a clipping container cannot cut it off", () => {
  const { container } = render(
    <div className="rail" style={{ overflow: "hidden", height: "40px" }}>
      <SourcePullMenu onPull={() => {}} />
    </div>,
  );
  fireEvent.click(screen.getByRole("button", { name: "pull specific sources" }));

  const menu = screen.getByRole("menu");
  expect(container.querySelector(".rail")).not.toContainElement(menu);
  expect(document.body).toContainElement(menu);
});
