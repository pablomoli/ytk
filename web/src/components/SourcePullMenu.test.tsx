import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { userEvent } from "@vitest/browser/context";
import { expect, test, vi } from "vitest";
import { SourcePullMenu } from "./SourcePullMenu";
import { PULL_SOURCES } from "./icons";

/* Radix attaches its outside-pointerdown listener a macrotask after open. */
const flushOpen = () =>
  act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });

test("lists every pullable source once opened", () => {
  render(<SourcePullMenu onPull={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Pull specific sources" }));

  for (const s of PULL_SOURCES) {
    expect(screen.getByRole("checkbox", { name: s })).toBeInTheDocument();
  }
});

/* The whole point of the feature: fetch from one named source on demand. */
test("pulls only the chosen sources", () => {
  const onPull = vi.fn();
  render(<SourcePullMenu onPull={onPull} />);
  fireEvent.click(screen.getByRole("button", { name: "Pull specific sources" }));

  fireEvent.click(screen.getByRole("checkbox", { name: "instagram" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^Pull/ }));

  expect(onPull).toHaveBeenCalledWith(["instagram"]);
});

test("the confirm button is inert until something is chosen", () => {
  render(<SourcePullMenu onPull={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Pull specific sources" }));
  expect(within(screen.getByRole("dialog")).getByRole("button", { name: /^Pull/ })).toBeDisabled();
});

test("uses an icon trigger but keeps the pull confirmation labeled", () => {
  render(<SourcePullMenu onPull={() => {}} />);
  const trigger = screen.getByRole("button", { name: "Pull specific sources" });
  expect(trigger).toHaveAttribute("data-slot", "icon-button");
  expect(trigger.getBoundingClientRect().width).toBeGreaterThanOrEqual(44);

  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("checkbox", { name: "youtube" }));
  expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Pull 1 source" })).toBeInTheDocument();
});

test("clicking inside the portaled popover does not dismiss it", async () => {
  render(<SourcePullMenu onPull={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Pull specific sources" }));
  await flushOpen();

  const box = screen.getByRole("checkbox", { name: "youtube" });
  fireEvent.pointerDown(box);
  fireEvent.click(box);

  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(box).toBeChecked();
});

test("closes on an outside pointerdown and on Escape", async () => {
  render(<SourcePullMenu onPull={() => {}} />);
  const caret = screen.getByRole("button", { name: "Pull specific sources" });

  fireEvent.click(caret);
  await flushOpen();
  /* A real browser click well away from the caret and the popover. */
  await userEvent.click(document.body, { position: { x: 300, y: 500 } });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  fireEvent.click(caret);
  await flushOpen();
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("renders outside the rail so a clipping container cannot cut it off", () => {
  const { container } = render(
    <div className="rail" style={{ overflow: "hidden", height: "40px" }}>
      <SourcePullMenu onPull={() => {}} />
    </div>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Pull specific sources" }));

  const menu = screen.getByRole("dialog");
  expect(container.querySelector(".rail")).not.toContainElement(menu);
  expect(document.body.contains(menu)).toBe(true);
});
