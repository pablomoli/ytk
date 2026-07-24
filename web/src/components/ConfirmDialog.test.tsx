import { StrictMode } from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { beforeAll, expect, test, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.open = true;
  };
  // Model the real browser: close() flips open synchronously but fires the
  // 'close' event on a queued task, not synchronously. A ref-flag guard set in
  // effect cleanup is already reset by StrictMode's remount before this event
  // arrives — a synchronous stub would hide that bug entirely.
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.open = false;
    queueMicrotask(() => this.dispatchEvent(new Event("close")));
  };
});

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
  fireEvent.click(screen.getByRole("button", { name: "delete", hidden: true }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
  expect(onCancel).not.toHaveBeenCalled();
});

test("cancel button fires onCancel", () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(<ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />);
  fireEvent.click(screen.getByRole("button", { name: "cancel", hidden: true }));
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onConfirm).not.toHaveBeenCalled();
});

test("backdrop click fires onCancel", () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const { container } = render(
    <ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />,
  );
  fireEvent.click(container.querySelector("dialog")!);
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onConfirm).not.toHaveBeenCalled();
});

test("escape (cancel event) fires onCancel", () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const { container } = render(
    <ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />,
  );
  fireEvent(container.querySelector("dialog")!, new Event("cancel", { cancelable: true }));
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onConfirm).not.toHaveBeenCalled();
});

test("survives StrictMode double-mount without firing onConfirm/onCancel (async close event)", async () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <StrictMode>
      <ConfirmDialog message="sure?" onConfirm={onConfirm} onCancel={onCancel} />
    </StrictMode>,
  );
  // Flush the close event the cleanup queued during the mount->cleanup->mount
  // cycle. A ref-flag guard would already be reset by the remount here, so
  // this asserts neither callback is coupled to the native close event.
  await act(async () => {
    await Promise.resolve();
  });
  expect(onConfirm).not.toHaveBeenCalled();
  expect(onCancel).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog", { hidden: true })).toBeInTheDocument();
});
