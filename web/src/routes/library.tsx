import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { FreshCard } from "../components/FreshCard";
import { MasonryGrid } from "../components/MasonryGrid";
import { NoteViewer } from "../components/NoteViewer";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { SourceFilter } from "../components/SourceFilter";
import { useDeleteNote } from "../api/fresh";
import type { FreshNote } from "../api/fresh";
import { useLibrary } from "../api/library";
import { HubControls } from "../components/HubControls";
import "../styles.css";

const PAGE = 60;

export const Route = createFileRoute("/library")({
  validateSearch: (search: Record<string, unknown>): { source?: string; q?: string } => ({
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
  const [selected, setSelected] = useState<FreshNote>();

  // filters reset pagination; a fetched page appends to the accumulated grid
  useEffect(() => { setPages([]); setOffset(0); }, [source, q]);
  useEffect(() => {
    if (page.data) setPages((current) => {
      const next = current.slice(0, offset / PAGE);
      next[offset / PAGE] = page.data.items;
      return next;
    });
  }, [page.data, offset]);

  const notes = pages.flat();
  const total = page.data?.total ?? 0;

  const handleDelete = (item: FreshNote) => {
    if (window.confirm("Delete this note for good? It leaves the vault and the search index.")) {
      remove.mutate(item.path, {
        onSuccess: () => {
          setPages((current) => current.map((chunk) => chunk.filter((n) => n.path !== item.path)));
          setSelected((current) => (current?.path === item.path ? undefined : current));
        },
      });
    }
  };

  let body;
  if (page.isLoading && !notes.length) {
    body = <MasonryGrid><Skeletons count={12} /></MasonryGrid>;
  } else if (page.isError) {
    body = <ErrorState error={page.error} />;
  } else if (!notes.length) {
    body = <EmptyState label={q ? "nothing matches" : "nothing ingested yet"} />;
  } else {
    body = <>
      <MasonryGrid>{notes.map((item) => <FreshCard key={item.path} note={item} onOpen={setSelected} onDelete={handleDelete} />)}</MasonryGrid>
      {notes.length < total ? (
        <div className="library-more">
          <button className="btn" type="button" disabled={page.isFetching} onClick={() => setOffset(notes.length)}>
            {page.isFetching ? "loading..." : `load more (${notes.length} of ${total})`}
          </button>
        </div>
      ) : null}
    </>;
  }

  return (
    <div id="library-page" className="hub-page">
      <HubControls>
        <input
          className="library-search"
          value={query}
          placeholder="filter title or tag..."
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void navigate({ search: { source, q: query.trim() || undefined } }); }}
        />
        <SourceFilter value={source} onChange={(next) => void navigate({ search: { source: next, q } })} />
        <span className="count">{total} in the store</span>
      </HubControls>
      <div className="hub-body">
        {remove.isError ? <div className="delete-error" role="alert">failed to delete note: {String(remove.error)}</div> : null}
        {body}
      </div>
      {selected ? <NoteViewer note={selected} onClose={() => setSelected(undefined)} /> : null}
    </div>
  );
}
