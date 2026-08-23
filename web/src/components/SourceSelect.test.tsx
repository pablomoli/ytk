import { act, fireEvent, render, screen } from "@testing-library/react";
import { userEvent } from "vitest/browser";
import { expect, test, vi } from "vitest";
import { SourceSelect } from "./SourceSelect";
import { SOURCES } from "./icons";
import { TooltipProvider } from "./ui/tooltip";

const renderSelect = (selection: React.ComponentProps<typeof SourceSelect>["selection"], onChange = () => {}) =>
  render(
    <TooltipProvider delayDuration={0}>
      <SourceSelect selection={selection} onChange={onChange} />
    </TooltipProvider>,
  );

test("exposes the sources as a named group of checkboxes", () => {
  renderSelect(null);

  const group = screen.getByRole("group", { name: /filter by source/i });
  expect(group).toBeInTheDocument();
  expect(screen.getAllByRole("checkbox")).toHaveLength(SOURCES.length);
});

test("every source starts checked now that none are hidden by default", () => {
  renderSelect(null);

  for (const box of screen.getAllByRole("checkbox")) expect(box).toBeChecked();
});

test("youtube and instagram can be checked together", () => {
  renderSelect(new Set(["youtube", "instagram"]));

  expect(screen.getByRole("checkbox", { name: /youtube/i })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /instagram/i })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /pinterest/i })).not.toBeChecked();
});

/* Toggling out of the default must materialize it first, or the first click
   would silently drop every other source. */
test("unchecking one source from the default keeps the others", () => {
  const onChange = vi.fn();
  renderSelect(null, onChange);

  fireEvent.click(screen.getByRole("checkbox", { name: /youtube/i }));

  const next = onChange.mock.calls[0][0] as Set<string>;
  expect(next.has("youtube")).toBe(false);
  expect(next.has("instagram")).toBe(true);
  expect(next.has("tiktok")).toBe(true);
});

/* Starts from a partial selection on purpose: with DEFAULT_HIDDEN empty the
   default already is every source, so the button is disabled there (covered
   below) and there would be nothing to widen. */
test("'all sources' selects every source", () => {
  const onChange = vi.fn();
  renderSelect(new Set(["youtube"]), onChange);

  fireEvent.click(screen.getByRole("button", { name: /select all sources/i }));

  expect(onChange.mock.calls[0][0]).toEqual(new Set(SOURCES));
});

test("'all sources' is disabled on the default, which now covers everything", () => {
  renderSelect(null);
  expect(screen.getByRole("button", { name: /select all sources/i })).toBeDisabled();
});

/* Reset is not "select everything" — it returns to the unchosen state, which
   re-applies DEFAULT_HIDDEN. That list is empty today, so the two buttons
   currently agree on the resulting set, but they must stay distinct calls:
   `null` means "not chosen" and tracks the default as it changes. */
test("'defaults' returns to the default rather than selecting everything", () => {
  const onChange = vi.fn();
  renderSelect(new Set(["tiktok"]), onChange);

  fireEvent.click(screen.getByRole("button", { name: /restore default sources/i }));

  expect(onChange).toHaveBeenCalledWith(null);
});

test("disables 'defaults' when already on the default", () => {
  renderSelect(null);
  expect(screen.getByRole("button", { name: /restore default sources/i })).toBeDisabled();
});

test("disables 'all sources' when everything is already selected", () => {
  renderSelect(new Set(SOURCES));
  expect(screen.getByRole("button", { name: /select all sources/i })).toBeDisabled();
});

test("source icons disclose their names on keyboard focus", async () => {
  renderSelect(null);
  const youtube = screen.getByRole("checkbox", { name: "youtube" });

  await act(async () => userEvent.click(youtube));

  expect(await screen.findByRole("tooltip")).toHaveTextContent("youtube");
});

test("bulk source actions are compact named icon controls", () => {
  renderSelect(new Set(["youtube"]));
  const selectAll = screen.getByRole("button", { name: "Select all sources" });
  const restore = screen.getByRole("button", { name: "Restore default sources" });

  expect(selectAll).toHaveAttribute("data-slot", "icon-button");
  expect(restore).toHaveAttribute("data-slot", "icon-button");
  expect(selectAll.getBoundingClientRect().width).toBeGreaterThanOrEqual(44);
  expect(restore.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
});
