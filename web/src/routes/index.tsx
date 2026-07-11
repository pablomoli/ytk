import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { FreshCard } from "../components/FreshCard";
import { MasonryGrid } from "../components/MasonryGrid";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { SourceFilter } from "../components/SourceFilter";
import { canonicalSource } from "../components/icons";
import { useDeleteNote, useFreshNotes, useNote, useSimilarNotes } from "../api/fresh";
import type { FreshNote } from "../api/fresh";
import { HubControls } from "../components/HubControls";
import "../styles.css";

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): { source?: string } => ({
    source: typeof search.source === "string" ? search.source : undefined,
  }),
  component: IndexPage,
});

function IndexPage() {
  const { source } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const fresh = useFreshNotes();
  const remove = useDeleteNote();
  const [selected, setSelected] = useState<FreshNote>();
  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const note = useNote(selected?.path);
  const similar = useSimilarNotes(selected?.path);
  const notes = useMemo(
    () => (fresh.data ?? []).filter((item) => !source || canonicalSource(item.source) === source || item.channel === source),
    [fresh.data, source],
  );

  const handleDelete = (item: FreshNote) => {
    if (window.confirm("Delete this note for good? It leaves the vault and the search index.")) {
      remove.mutate(item.path, { onSuccess: () => setSelected((current) => (current?.path === item.path ? undefined : current)) });
    }
  };

  useEffect(() => {
    if (!selected) return;
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const close = dialogRef.current?.querySelector<HTMLElement>(".viewer-close");
    close?.focus();
    return () => restoreFocusRef.current?.focus();
  }, [selected]);

  const handleDialogKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setSelected(undefined);
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = [...(dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    ) ?? [])];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1)!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  let body;
  if (fresh.isLoading) {
    body = <MasonryGrid><Skeletons count={12} /></MasonryGrid>;
  } else if (fresh.isError) {
    body = <ErrorState error={fresh.error} />;
  } else if (!notes.length) {
    body = <EmptyState label="nothing ingested yet" />;
  } else {
    body = <MasonryGrid>{notes.map((item) => <FreshCard key={item.path} note={item} onOpen={setSelected} onDelete={handleDelete} />)}</MasonryGrid>;
  }

  return (
    <div id="fresh-page" className="hub-page">
      <HubControls>
        <SourceFilter value={source} onChange={(next) => void navigate({ search: { source: next } })} />
        <span className="count">{notes.length} recently ingested</span>
      </HubControls>
      <div className="hub-body">
        {remove.isError ? <div className="delete-error" role="alert">failed to delete note: {String(remove.error)}</div> : null}
        {body}
      </div>
      {selected ? (
        <div ref={dialogRef} className="note-viewer" role="dialog" aria-modal="true" aria-label={selected.title} onKeyDown={handleDialogKeyDown} onClick={() => setSelected(undefined)}>
          <div className="note-panel" onClick={(event) => event.stopPropagation()}>
            <button className="btn viewer-close" type="button" onClick={() => setSelected(undefined)}>close</button>
            {note.isLoading ? <p>loading note...</p> : null}
            {note.isError ? <p>failed to load note: {String(note.error)}</p> : null}
            {note.data ? <pre>{note.data.content}</pre> : null}
            {similar.data?.length ? (
              <div className="similar-items">
                <span>visually similar</span>
                {similar.data.map((item) => (
                  <a key={item.item_id} href={item.url || "#"} target="_blank" rel="noreferrer" title={item.title || item.item_id}>
                    <img src={`/api/visual-image?id=${encodeURIComponent(item.item_id)}`} loading="lazy" alt="" />
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
