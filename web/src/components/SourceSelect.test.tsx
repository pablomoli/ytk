import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { SourceSelect } from "./SourceSelect";
import { SOURCES } from "./icons";

test("exposes the sources as a named group of checkboxes", () => {
  render(<SourceSelect selection={null} onChange={() => {}} />);

  const group = screen.getByRole("group", { name: /filter by source/i });
  expect(group).toBeInTheDocument();
  expect(screen.getAllByRole("checkbox")).toHaveLength(SOURCES.length);
});

test("every source starts checked now that none are hidden by default", () => {
  render(<SourceSelect selection={null} onChange={() => {}} />);

  for (const box of screen.getAllByRole("checkbox")) expect(box).toBeChecked();
});

test("youtube and instagram can be checked together", () => {
  render(<SourceSelect selection={new Set(["youtube", "instagram"])} onChange={() => {}} />);

  expect(screen.getByRole("checkbox", { name: /youtube/i })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /instagram/i })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /pinterest/i })).not.toBeChecked();
});

/* Toggling out of the default must materialize it first, or the first click
   would silently drop every other source. */
test("unchecking one source from the default keeps the others", () => {
  const onChange = vi.fn();
  render(<SourceSelect selection={null} onChange={onChange} />);

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
  render(<SourceSelect selection={new Set(["youtube"])} onChange={onChange} />);

  fireEvent.click(screen.getByRole("button", { name: /all sources/i }));

  expect(onChange.mock.calls[0][0]).toEqual(new Set(SOURCES));
});

test("'all sources' is disabled on the default, which now covers everything", () => {
  render(<SourceSelect selection={null} onChange={() => {}} />);
  expect(screen.getByRole("button", { name: /all sources/i })).toBeDisabled();
});

/* Reset is not "select everything" — it returns to the unchosen state, which
   re-applies DEFAULT_HIDDEN. That list is empty today, so the two buttons
   currently agree on the resulting set, but they must stay distinct calls:
   `null` means "not chosen" and tracks the default as it changes. */
test("'defaults' returns to the default rather than selecting everything", () => {
  const onChange = vi.fn();
  render(<SourceSelect selection={new Set(["tiktok"])} onChange={onChange} />);

  fireEvent.click(screen.getByRole("button", { name: /defaults/i }));

  expect(onChange).toHaveBeenCalledWith(null);
});

test("disables 'defaults' when already on the default", () => {
  render(<SourceSelect selection={null} onChange={() => {}} />);
  expect(screen.getByRole("button", { name: /defaults/i })).toBeDisabled();
});

test("disables 'all sources' when everything is already selected", () => {
  render(<SourceSelect selection={new Set(SOURCES)} onChange={() => {}} />);
  expect(screen.getByRole("button", { name: /all sources/i })).toBeDisabled();
});
