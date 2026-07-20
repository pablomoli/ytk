import { useEffect, useRef } from 'react'

/* Themed replacement for window.confirm, built on native <dialog> like
   NoteViewer. onConfirm/onCancel are driven ONLY by explicit user intent —
   never by the native 'close' event, which fires asynchronously (a queued
   task). A ref-flag guard set in effect cleanup would already be reset by
   StrictMode's remount before that queued event arrives, firing a spurious
   callback a frame after opening. So: showModal in an effect, cleanup just
   closes the dialog; Escape routes through onCancel via the 'cancel' event;
   the cancel button and backdrop call onCancel directly; the confirm button
   calls onConfirm directly. React unmount then closes the dialog in cleanup
   with nothing wired to that close. */
export function ConfirmDialog({ message, confirmLabel = 'delete', onConfirm, onCancel }: {
  message: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (!dialog.open) dialog.showModal?.()
    return () => dialog.close?.()
  }, [])

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-label={message}
      onCancel={(event) => { event.preventDefault(); onCancel() }}
      onClick={(event) => { if (event.target === dialogRef.current) onCancel() }}
    >
      <p>{message}</p>
      <div className="confirm-actions">
        <button className="btn" type="button" onClick={onCancel}>cancel</button>
        <button className="btn primary" type="button" onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </dialog>
  )
}
