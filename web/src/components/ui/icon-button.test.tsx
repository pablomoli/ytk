import { act, fireEvent, render, screen } from "@testing-library/react";
import { ArrowsClockwiseIcon } from "@phosphor-icons/react";
import { expect, test, vi } from "vite-plus/test";
import { userEvent } from "vite-plus/test/browser";
import { IconButton } from "./icon-button";
import { TooltipProvider } from "./tooltip";

function renderIconButton(onClick = () => {}) {
  render(
    <TooltipProvider delayDuration={0}>
      <IconButton label="refresh" onClick={onClick}>
        <ArrowsClockwiseIcon role="img" aria-label="reload graphic" data-testid="refresh-icon" />
      </IconButton>
    </TooltipProvider>,
  );
  return screen.getByRole("button", { name: "refresh" });
}

test("uses its label as the accessible name and hides the icon subtree", () => {
  const button = renderIconButton();

  expect(button).toHaveAccessibleName("refresh");
  expect(screen.queryByRole("img", { name: "reload graphic" })).not.toBeInTheDocument();
  expect(screen.getByTestId("refresh-icon").parentElement).toHaveAttribute("aria-hidden", "true");
});

test("shows the label as supplemental help when focused", async () => {
  const button = renderIconButton();

  await act(async () => userEvent.tab());

  expect(button).toHaveFocus();
  expect(await screen.findByRole("tooltip")).toHaveTextContent("refresh");
});

test("forwards activation to the caller", () => {
  const onClick = vi.fn();
  const button = renderIconButton(onClick);

  fireEvent.click(button);

  expect(onClick).toHaveBeenCalledTimes(1);
});

test("keeps a 44px square product target", () => {
  const target = renderIconButton().getBoundingClientRect();

  expect(target.height).toBeGreaterThanOrEqual(44);
  expect(target.width).toBeGreaterThanOrEqual(44);
});
