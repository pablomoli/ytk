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

test("reddit starts unchecked and everything else starts checked", () => {
  render(<SourceSelect selection={null} onChange={() => {}} />);

  expect(screen.getByRole("checkbox", { name: /reddit/i })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: /youtube/i })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /instagram/i })).toBeChecked();
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
  expect(next.has("reddit")).toBe(false);
});

test("reddit can be opted into explicitly", () => {
  const onChange = vi.fn();
  render(<SourceSelect selection={null} onChange={onChange} />);

  fireEvent.click(screen.getByRole("checkbox", { name: /reddit/i }));

  expect((onChange.mock.calls[0][0] as Set<string>).has("reddit")).toBe(true);
});

test("'all sources' selects every source, including the hidden ones", () => {
  const onChange = vi.fn();
  render(<SourceSelect selection={null} onChange={onChange} />);

  fireEvent.click(screen.getByRole("button", { name: /all sources/i }));

  expect(onChange.mock.calls[0][0]).toEqual(new Set(SOURCES));
});

/* Reset is not "select everything" — it returns to the default, which re-hides
   the excluded sources. The two buttons must not collapse into one behaviour. */
test("'defaults' returns to the default rather than selecting everything", () => {
  const onChange = vi.fn();
  render(<SourceSelect selection={new Set(["reddit"])} onChange={onChange} />);

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
