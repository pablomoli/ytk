import { StrictMode, useRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useModalDialog } from "./useModalDialog";

function Harness({ onCancel }: { onCancel: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useModalDialog(dialogRef);

  return (
    <dialog
      ref={dialogRef}
      aria-label="modal harness"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    />
  );
}

test("opens the dialog modally under StrictMode", () => {
  render(
    <StrictMode>
      <Harness onCancel={() => {}} />
    </StrictMode>,
  );

  expect(screen.getByRole("dialog", { hidden: true })).toHaveAttribute("open");
});

test("leaves Escape intent with the consumer", () => {
  const onCancel = vi.fn();
  render(<Harness onCancel={onCancel} />);

  fireEvent(
    screen.getByRole("dialog", { hidden: true }),
    new Event("cancel", { cancelable: true }),
  );

  expect(onCancel).toHaveBeenCalledTimes(1);
});

test("closes on unmount without reporting user intent", () => {
  const onCancel = vi.fn();
  const close = vi.spyOn(HTMLDialogElement.prototype, "close");
  const { unmount } = render(<Harness onCancel={onCancel} />);

  unmount();

  expect(close).toHaveBeenCalledTimes(1);
  expect(onCancel).not.toHaveBeenCalled();
});
