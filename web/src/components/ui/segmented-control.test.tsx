import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vite-plus/test";
import { SegmentedControl, SegmentedControlItem } from "./segmented-control";

function renderControl(onValueChange = () => {}) {
  render(
    <SegmentedControl label="View" value="list" onValueChange={onValueChange}>
      <SegmentedControlItem value="list">list</SegmentedControlItem>
      <SegmentedControlItem value="grid">grid</SegmentedControlItem>
    </SegmentedControl>,
  );
}

test("is visibly labeled and exposes the controlled single selection", () => {
  renderControl();

  expect(screen.getByText("View")).toBeVisible();
  expect(screen.getByRole("radiogroup", { name: "View" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "list" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "grid" })).not.toBeChecked();
});

test("emits the next single selection", () => {
  const onValueChange = vi.fn();
  renderControl(onValueChange);

  fireEvent.click(screen.getByRole("radio", { name: "grid" }));

  expect(onValueChange).toHaveBeenCalledOnce();
  expect(onValueChange).toHaveBeenCalledWith("grid");
});

test("ignores an empty deselection of the active item", () => {
  const onValueChange = vi.fn();
  renderControl(onValueChange);

  fireEvent.click(screen.getByRole("radio", { name: "list" }));

  expect(onValueChange).not.toHaveBeenCalled();
});

test("keeps 44px item targets", () => {
  renderControl();

  for (const item of screen.getAllByRole("radio")) {
    const target = item.getBoundingClientRect();
    expect(target.height).toBeGreaterThanOrEqual(44);
    expect(target.width).toBeGreaterThanOrEqual(44);
  }
});
