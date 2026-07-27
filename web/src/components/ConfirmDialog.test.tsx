import { StrictMode } from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { userEvent } from "@vitest/browser/context";
import { expect, test, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

test("confirm fires onConfirm once, not onCancel", () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      message="delete this note for good?"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />,
  );
  expect(screen.getByText("delete this note for good?")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "delete" }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
  expect(onCancel).not.toHaveBeenCalled();
});

test("cancel button fires onCancel", () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(<ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />);
  fireEvent.click(screen.getByRole("button", { name: "cancel" }));
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onConfirm).not.toHaveBeenCalled();
});

test("overlay click fires onCancel", async () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(<ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />);
  /* Radix attaches its outside-pointerdown listener a macrotask after mount. */
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  const overlay = document.querySelector<HTMLElement>('[data-slot="dialog-overlay"]')!;
  /* A real browser click at the corner, clear of the centered panel. */
  await userEvent.click(overlay, { position: { x: 5, y: 5 } });
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onConfirm).not.toHaveBeenCalled();
});

test("escape fires onCancel", () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(<ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onConfirm).not.toHaveBeenCalled();
});

test("focus starts inside the dialog", () => {
  render(<ConfirmDialog message="sure?" onConfirm={() => {}} onCancel={() => {}} />);
  expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
});

test("survives StrictMode double-mount without firing onConfirm/onCancel", async () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <StrictMode>
      <ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />
    </StrictMode>,
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(onConfirm).not.toHaveBeenCalled();
  expect(onCancel).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});
