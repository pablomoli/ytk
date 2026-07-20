import { useEffect, useRef } from 'react'
import type { FreshNote } from '../api/fresh'
import { useNote, useSimilarNotes } from '../api/fresh'

/* Native <dialog> gives the platform behaviors the old hand-rolled viewers
   faked or lacked: top-layer stacking, inert background, focus trap, focus
   restore on close, Escape (the dialog fires 'close'), and ::backdrop. */
export function NoteViewer({ note, onClose }: { note: FreshNote; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const content = useNote(note.path)
  const similar = useSimilarNotes(note.path)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (!dialog.open) dialog.showModal?.()
    return () => dialog.close?.()
  }, [])

  /* onClose is driven ONLY by explicit user intent — never by the native
     'close' event. That event is fired asynchronously, so a ref flag set in
     effect cleanup is already reset by StrictMode's remount before the queued
     event arrives. Instead, Escape routes through onCancel and the button and
     backdrop call onClose directly; React unmount then closes the dialog in
     cleanup, and the programmatic close() has nothing wired to it. */
  return (
    <dialog
      ref={dialogRef}
      className="note-viewer"
      aria-label={note.title}
      onCancel={(event) => { event.preventDefault(); onClose() }}
      onClick={(event) => { if (event.target === dialogRef.current) onClose() }}
    >
      <div className="note-panel">
        <button className="btn viewer-close" type="button" onClick={onClose}>close</button>
        {content.isLoading ? <p>loading note...</p> : null}
        {content.isError ? <p>failed to load note: {String(content.error)}</p> : null}
        {content.data ? <pre>{content.data.content}</pre> : null}
        {similar.data?.length ? (
          <div className="similar-items">
            <span>visually similar</span>
            {similar.data.map((item) => (
              <a key={item.item_id} href={item.url || '#'} target="_blank" rel="noreferrer" title={item.title || item.item_id}>
                <img src={`/api/visual-image?id=${encodeURIComponent(item.item_id)}`} loading="lazy" alt="" />
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </dialog>
  )
}
