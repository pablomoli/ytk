import { useState } from "react";
import type { QueueItem } from "../api/queue";
import { sourceIcon } from "./icons";
import { isOpenable, provenance } from "../lib/provenance";
import { capturedLabel } from "../lib/captured";
import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";

/* Inspecting a pending item without ingesting or selecting it (#123).

   Deliberately a different surface from NoteViewer: that one reads an ingested
   note out of the vault, and nothing here has been ingested yet. All this can
   show is what the queue row carries, so it shows that honestly rather than
   fetching anything. Sized narrower and content-height, unlike NoteViewer:
   nothing here has been ingested, so a page-sized frame would promise
   content that does not exist yet. */
export function QueueItemViewer({
  item,
  selected,
  onToggleSelect,
  onClose,
}: {
  item: QueueItem;
  selected: boolean;
  onToggleSelect: (i: QueueItem) => void;
  onClose: () => void;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const { domain, community } = provenance(item.url);
  const captured = capturedLabel(item.shared_at);

  const showImage = Boolean(item.preview_url) && !imageFailed;

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent
        className="max-h-[calc(100vh-4rem)] w-[min(100vw-4rem,34rem)] p-0"
        aria-describedby={undefined}
      >
        <DialogTitle className="sr-only">{`Pending ${item.source} item`}</DialogTitle>
        <div className="queue-panel">
          <button className="btn viewer-close" type="button" onClick={onClose}>
            close
          </button>

          <div className="queue-panel-head">
            {sourceIcon(item.source)}
            <span data-testid="viewer-source">{item.source}</span>
            {community || domain ? (
              <span className="queue-place" data-testid="viewer-place">
                {community || domain}
              </span>
            ) : null}
          </div>

          {showImage ? (
            <img
              className="queue-preview"
              src={item.preview_url}
              alt=""
              onError={() => setImageFailed(true)}
            />
          ) : (
            /* The explicit unavailable state the issue asks for. An item with no
             usable asset still has provenance and text worth reading, so the
             panel says the preview is missing instead of leaving a dead box. */
            <p className="queue-nopreview" data-testid="viewer-nopreview">
              no preview available
            </p>
          )}

          {item.text ? (
            <p className="queue-text">{item.text}</p>
          ) : (
            <p className="queue-text queue-text-empty">no captured text</p>
          )}

          <dl className="queue-facts">
            {item.author ? (
              <>
                <dt>author</dt>
                <dd data-testid="viewer-author">{item.author}</dd>
              </>
            ) : null}
            {captured ? (
              <>
                <dt>captured</dt>
                <dd>
                  <time dateTime={item.shared_at}>{captured}</time>
                </dd>
              </>
            ) : null}
            <dt>url</dt>
            <dd className="queue-url">{item.url}</dd>
          </dl>

          <div className="queue-panel-actions">
            {isOpenable(item.url) ? (
              <a
                className="btn primary"
                href={item.url}
                target="_blank"
                rel="noreferrer"
                data-testid="viewer-open"
              >
                open original
              </a>
            ) : (
              /* An iMessage capture's url is a synthetic session id, not a link.
               Saying so beats a button that navigates nowhere. */
              <span className="queue-nolink" data-testid="viewer-nolink">
                no original to open
              </span>
            )}
            <button
              className="btn"
              type="button"
              role="checkbox"
              aria-checked={selected}
              onClick={() => onToggleSelect(item)}
            >
              {selected ? "deselect" : "select"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
