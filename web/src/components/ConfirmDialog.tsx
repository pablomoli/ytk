import { useRef } from "react";
import { useModalDialog } from "../lib/useModalDialog";

/* User intent is handled explicitly; lifecycle cleanup never invokes a
   confirm or cancel callback. */
export function ConfirmDialog({
  message,
  confirmLabel = "delete",
  onConfirm,
  onCancel,
}: {
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useModalDialog(dialogRef);

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-label={message}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) onCancel();
      }}
    >
      <p>{message}</p>
      <div className="confirm-actions">
        <button className="btn" type="button" onClick={onCancel}>
          cancel
        </button>
        <button className="btn primary" type="button" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
