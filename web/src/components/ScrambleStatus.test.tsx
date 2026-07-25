import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ScrambleStatus } from "./ScrambleStatus";

test("renders the target text (scramble is enhancement only)", () => {
  render(<ScrambleStatus text="running" />);
  expect(screen.getByText("running")).toBeInTheDocument();
});

test("updates to new text on prop change", () => {
  const { rerender } = render(<ScrambleStatus text="running" />);
  rerender(<ScrambleStatus text="done" />);
  expect(screen.getByText("done")).toBeInTheDocument();
});
