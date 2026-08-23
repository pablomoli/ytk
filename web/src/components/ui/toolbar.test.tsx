import { act, render, screen } from "@testing-library/react";
import { expect, test } from "vite-plus/test";
import { userEvent } from "vite-plus/test/browser";
import { Toolbar, ToolbarButton } from "./toolbar";

test("provides named horizontal roving focus with Arrow, Home, and End navigation", async () => {
  render(
    <Toolbar label="Map camera">
      <ToolbarButton>home</ToolbarButton>
      <ToolbarButton>zoom out</ToolbarButton>
      <ToolbarButton>reset</ToolbarButton>
    </Toolbar>,
  );

  expect(screen.getByRole("toolbar", { name: "Map camera" })).toBeInTheDocument();

  const home = screen.getByRole("button", { name: "home" });
  const zoomOut = screen.getByRole("button", { name: "zoom out" });
  const reset = screen.getByRole("button", { name: "reset" });

  await act(async () => userEvent.tab());
  expect(home).toHaveFocus();

  await act(async () => userEvent.keyboard("{ArrowRight}"));
  expect(zoomOut).toHaveFocus();

  await act(async () => userEvent.keyboard("{End}"));
  expect(reset).toHaveFocus();

  await act(async () => userEvent.keyboard("{Home}"));
  expect(home).toHaveFocus();
});
