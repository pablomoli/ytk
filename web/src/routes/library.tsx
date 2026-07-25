import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FreshCard } from "../components/FreshCard";
import { MasonryGrid } from "../components/MasonryGrid";
import { NoteViewer } from "../components/NoteViewer";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { SourceFilter } from "../components/SourceFilter";
import { TargetCursor } from "../components/TargetCursor";
import { useDeleteNote } from "../api/fresh";
import type { FreshNote } from "../api/fresh";
import { useLibrary } from "../api/library";
import { HubControls } from "../components/HubControls";
import { CountUp } from "../components/CountUp";
import { CURSOR_PREF, getPref } from "../lib/prefs";
import "../styles.css";

const PAGE = 60;

export const Route = createFileRoute("/library")({
  validateSearch: (
    search: Record<string, unknown>,
  ): { source?: string | undefined; q?: string | undefined } => ({
    source: typeof search.source === "string" ? search.source : undefined,
    q: typeof search.q === "string" ? search.q : undefined,
  }),
  component: LibraryPage,
});

function LibraryPage() {
  const { source, q } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const [pages, setPages] = useState<FreshNote[][]>([]);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState(q ?? "");
  const page = useLibrary(offset, source, q, PAGE);
  const remove = useDeleteNote();
  const [selected, setSelected] = useState<{ note: FreshNote; rect?: DOMRect | undefined }>();
  const [pendingDelete, setPendingDelete] = useState<FreshNote>();

  // filters reset pagination; a fetched page appends to the accumulated grid
  useEffect(() => {
    setPages([]);
    setOffset(0);
  }, [source, q]);
  useEffect(() => {
    if (page.data)
      setPages((current) => {
        const next = current.slice(0, offset / PAGE);
        next[offset / PAGE] = page.data.items;
        return next;
      });
  }, [page.data, offset]);

  const notes = pages.flat();
  const total = page.data?.total ?? 0;

  const handleDelete = (item: FreshNote) => setPendingDelete(item);

  let body;
  if (page.isLoading && !notes.length) {
    body = (
      <MasonryGrid>
        <Skeletons count={12} />
      </MasonryGrid>
    );
  } else if (page.isError) {
    body = <ErrorState error={page.error} onRetry={() => void page.refetch()} />;
  } else if (!notes.length) {
    body = (
      <EmptyState
        label={q ? "nothing matches" : "nothing ingested yet"}
        hint={q ? "try a looser query" : undefined}
      />
    );
  } else {
    body = (
      <>
        <MasonryGrid>
          {notes.map((item) => (
            <FreshCard
              key={item.path}
              note={item}
              onOpen={(note, rect) => setSelected({ note, rect })}
              onDelete={handleDelete}
            />
          ))}
        </MasonryGrid>
        {notes.length < total ? (
          <div className="library-more">
            <button
              className="btn"
              type="button"
              disabled={page.isFetching}
              onClick={() => setOffset(notes.length)}
            >
              {page.isFetching ? "loading..." : `load more (${notes.length} of ${total})`}
            </button>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <div id="library-page" className="hub-page">
      <HubControls>
        <input
          className="library-search"
          value={query}
          placeholder="filter title or tag..."
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter")
              void navigate({ search: { source, q: query.trim() || undefined } });
          }}
        />
        <SourceFilter
          value={source}
          onChange={(next) => void navigate({ search: { source: next, q } })}
        />
        <span className="count">
          <CountUp value={total} /> in the store
        </span>
      </HubControls>
      <div className="hub-body">
        {remove.isError ? (
          <div className="delete-error" role="alert">
            failed to delete note: {String(remove.error)}
          </div>
        ) : null}
        {body}
      </div>
      {selected ? (
        <NoteViewer
          note={selected.note}
          originRect={selected.rect}
          onClose={() => setSelected(undefined)}
        />
      ) : null}
      {getPref(CURSOR_PREF) ? <TargetCursor /> : null}
      {pendingDelete ? (
        <ConfirmDialog
          message="delete this note for good? it leaves the vault and the search index."
          onCancel={() => setPendingDelete(undefined)}
          onConfirm={() => {
            const item = pendingDelete;
            setPendingDelete(undefined);
            remove.mutate(item.path, {
              onSuccess: () => {
                setPages((current) =>
                  current.map((chunk) => chunk.filter((n) => n.path !== item.path)),
                );
                setSelected((current) => (current?.note.path === item.path ? undefined : current));
              },
            });
          }}
        />
      ) : null}
    </div>
  );
}
