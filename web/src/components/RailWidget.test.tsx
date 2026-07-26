import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { RailWidget } from "./RailWidget";
import { getPref } from "../lib/prefs";

beforeEach(() => localStorage.clear());

const open = (title: string) =>
  (screen.getByText(title).closest("details") as HTMLDetailsElement).open;

test("uses its declared default when no pref is stored", () => {
  render(
    <>
      <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
        <p>q body</p>
      </RailWidget>
      <RailWidget title="match" prefKey="ytk:test:m">
        <p>m body</p>
      </RailWidget>
    </>,
  );
  expect(open("queue")).toBe(true);
  expect(open("match")).toBe(false);
});

test("a stored pref overrides the default", () => {
  localStorage.setItem("ytk:test:q", "0");
  render(
    <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
      <p>q body</p>
    </RailWidget>,
  );
  expect(open("queue")).toBe(false);
});

test("toggling persists the new state", async () => {
  render(
    <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
      <p>q body</p>
    </RailWidget>,
  );
  screen.getByText("queue").click();
  expect(open("queue")).toBe(false);
  // the toggle event is queued as a task, so the pref write trails the click
  await waitFor(() => expect(getPref("ytk:test:q", true)).toBe(false));
});

test("widgets toggle independently", () => {
  render(
    <>
      <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
        <p>q body</p>
      </RailWidget>
      <RailWidget title="match" prefKey="ytk:test:m" defaultOpen>
        <p>m body</p>
      </RailWidget>
    </>,
  );
  screen.getByText("queue").click();
  expect(open("queue")).toBe(false);
  expect(open("match")).toBe(true);
});

test("uses native details and summary rather than hand-rolled ARIA", () => {
  const { container } = render(
    <RailWidget title="queue" prefKey="ytk:test:q">
      <p>q body</p>
    </RailWidget>,
  );
  expect(container.querySelector("details")).toBeTruthy();
  expect(container.querySelector("summary")).toBeTruthy();
  expect(container.querySelector("[aria-expanded]")).toBeNull();
});

test("forceOpenKey opens the widget when it changes to a new value", () => {
  const { rerender } = render(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey={null}>
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(false);
  rerender(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(true);
});

test("forceOpenKey does not reopen after the user closes it", () => {
  const { rerender } = render(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(true);
  screen.getByText("job").click();
  expect(open("job")).toBe(false);
  rerender(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(false);
});

test("forceOpenKey opens again when a new job starts after the user closed it", () => {
  const { rerender } = render(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(true);
  screen.getByText("job").click();
  expect(open("job")).toBe(false);
  rerender(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-2">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(true);
});

test("forceOpenKey opens again for a new job with the same key, once the previous job ends", () => {
  const { rerender } = render(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(true);
  screen.getByText("job").click();
  expect(open("job")).toBe(false);
  rerender(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey={null}>
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(false);
  rerender(
    <RailWidget title="job" prefKey="ytk:test:j" forceOpenKey="job-1">
      <p>j body</p>
    </RailWidget>,
  );
  expect(open("job")).toBe(true);
});

/* The bug this whole browser migration exists for (#135). A controlled open
   attribute and the browser's default action both flip it on a summary click,
   so they cancel and the first click does nothing.

   This must use userEvent, not element.click(): a synthetic dispatch does not
   reproduce the ordering between React's handler and the browser's default
   action, and passes against the broken component. userEvent drives a real
   trusted click through the browser, which is the only thing that catches it. */
test("one real click toggles a section, in both directions", async () => {
  render(
    <RailWidget title="queue" prefKey="ytk:test:q" defaultOpen>
      <p>q body</p>
    </RailWidget>,
  );
  expect(open("queue")).toBe(true);

  await userEvent.click(screen.getByText("queue"));
  expect(open("queue")).toBe(false);

  await userEvent.click(screen.getByText("queue"));
  expect(open("queue")).toBe(true);
});
