import { act, render, screen, fireEvent } from "@testing-library/react";
import { userEvent } from "vitest/browser";
import { expect, test, vi } from "vitest";
import { SourceFilter } from "./SourceFilter";
import { TooltipProvider } from "./ui/tooltip";

const renderFilter = (value: string | undefined, onChange = (_source?: string) => {}) =>
  render(
    <TooltipProvider delayDuration={0}>
      <SourceFilter value={value} onChange={onChange} />
    </TooltipProvider>,
  );

test("toggles source", () => {
  const onChange = vi.fn();
  const { rerender } = renderFilter(undefined, onChange);
  fireEvent.click(screen.getByText("youtube"));
  expect(onChange).toHaveBeenCalledWith("youtube");
  rerender(<SourceFilter value="youtube" onChange={onChange} />);
  fireEvent.click(screen.getByText("youtube"));
  expect(onChange).toHaveBeenCalledWith(undefined);
});

test("renders the discovery sources as filter chips", () => {
  const onChange = vi.fn();
  renderFilter(undefined, onChange);
  for (const s of ["tiktok", "reddit", "instagram", "youtube"]) {
    fireEvent.click(screen.getByText(s));
    expect(onChange).toHaveBeenCalledWith(s);
  }
});

test("chips carry aria-pressed reflecting selection", () => {
  const { rerender } = renderFilter(undefined);
  expect(screen.getByRole("button", { name: "youtube" })).toHaveAttribute("aria-pressed", "false");
  rerender(<SourceFilter value="youtube" onChange={() => {}} />);
  expect(screen.getByRole("button", { name: "youtube" })).toHaveAttribute("aria-pressed", "true");
});

test("uses a named toolbar with roving arrow-key focus", async () => {
  renderFilter(undefined);
  expect(screen.getByRole("toolbar", { name: "Filter by source" })).toBeInTheDocument();

  await act(async () => userEvent.tab());
  const buttons = screen.getAllByRole("button");
  expect(buttons[0]).toHaveFocus();
  await act(async () => userEvent.keyboard("{ArrowRight}"));
  expect(buttons[1]).toHaveFocus();
});

test("source filter controls keep 44px product targets", () => {
  renderFilter(undefined);
  for (const button of screen.getAllByRole("button")) {
    const bounds = button.getBoundingClientRect();
    expect(bounds.width).toBeGreaterThanOrEqual(44);
    expect(bounds.height).toBeGreaterThanOrEqual(44);
  }
});
