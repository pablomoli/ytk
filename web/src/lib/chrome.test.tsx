import { render, screen, fireEvent } from "@testing-library/react";
import { expect, test } from "vitest";
import { ChromeProvider, useChromeVisible } from "./chrome";

function Probe() {
  return <span>{useChromeVisible() ? "shown" : "hidden"}</span>;
}

test("chrome is visible outside a provider", () => {
  render(<Probe />);
  expect(screen.getByText("shown")).toBeTruthy();
});

test("period toggles chrome off and back on", () => {
  render(
    <ChromeProvider>
      <Probe />
    </ChromeProvider>,
  );
  expect(screen.getByText("shown")).toBeTruthy();
  fireEvent.keyDown(window, { key: "." });
  expect(screen.getByText("hidden")).toBeTruthy();
  fireEvent.keyDown(window, { key: "." });
  expect(screen.getByText("shown")).toBeTruthy();
});

test("period while typing does not toggle", () => {
  render(
    <ChromeProvider>
      <input aria-label="q" />
      <Probe />
    </ChromeProvider>,
  );
  fireEvent.keyDown(screen.getByLabelText("q"), { key: "." });
  expect(screen.getByText("shown")).toBeTruthy();
});

test("a modified period does not toggle", () => {
  render(
    <ChromeProvider>
      <Probe />
    </ChromeProvider>,
  );
  fireEvent.keyDown(window, { key: ".", metaKey: true });
  expect(screen.getByText("shown")).toBeTruthy();
});
