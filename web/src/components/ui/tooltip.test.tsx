import { act, render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vite-plus/test";
import { userEvent } from "vite-plus/test/browser";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./tooltip";

function renderTooltip() {
  render(
    <TooltipProvider delayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button aria-label="refresh">reload</button>
        </TooltipTrigger>
        <TooltipContent>Fetch new items</TooltipContent>
      </Tooltip>
    </TooltipProvider>,
  );
  return screen.getByRole("button", { name: "refresh" });
}

test("opens on hover and closes when the pointer leaves", async () => {
  const trigger = renderTooltip();

  await act(async () => userEvent.hover(trigger));
  expect(await screen.findByRole("tooltip")).toHaveTextContent("Fetch new items");

  await act(async () => userEvent.unhover(trigger));
  await waitFor(() => expect(screen.queryByRole("tooltip")).not.toBeInTheDocument());
});

test("opens on focus and closes on Escape without moving focus", async () => {
  const trigger = renderTooltip();

  await act(async () => userEvent.tab());
  expect(trigger).toHaveFocus();
  expect(await screen.findByRole("tooltip")).toBeInTheDocument();

  await act(async () => userEvent.keyboard("{Escape}"));
  await waitFor(() => expect(screen.queryByRole("tooltip")).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
});

test("supplements rather than creates the trigger's accessible name", () => {
  const trigger = renderTooltip();

  expect(trigger).toHaveAccessibleName("refresh");
  expect(trigger).not.toHaveAccessibleName("Fetch new items");
});
