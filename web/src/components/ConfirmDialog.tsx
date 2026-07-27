import { Dialog, DialogContent, DialogFooter, DialogTitle } from "./ui/dialog";

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
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <DialogContent aria-describedby={undefined}>
        <DialogTitle>{message}</DialogTitle>
        <DialogFooter>
          <button className="btn" type="button" onClick={onCancel}>
            cancel
          </button>
          <button className="btn primary" type="button" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
