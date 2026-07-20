import { useMemo, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { FreshCard } from "../components/FreshCard";
import { MasonryGrid } from "../components/MasonryGrid";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { NoteViewer } from "../components/NoteViewer";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { SourceFilter } from "../components/SourceFilter";
import { TargetCursor } from "../components/TargetCursor";
import { canonicalSource } from "../components/icons";
import { useDeleteNote, useFreshNotes } from "../api/fresh";
import type { FreshNote } from "../api/fresh";
import { HubControls } from "../components/HubControls";
import { CountUp } from "../components/CountUp";
import { CURSOR_PREF, getPref } from "../lib/prefs";
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
  const [selected, setSelected] = useState<{ note: FreshNote; rect?: DOMRect }>();
  const [pendingDelete, setPendingDelete] = useState<FreshNote>();
  const notes = useMemo(
    () => (fresh.data ?? []).filter((item) => !source || canonicalSource(item.source) === source || item.channel === source),
    [fresh.data, source],
  );

  const handleDelete = (item: FreshNote) => setPendingDelete(item);

  let body;
  if (fresh.isLoading) {
    body = <MasonryGrid><Skeletons count={12} /></MasonryGrid>;
  } else if (fresh.isError) {
    body = <ErrorState error={fresh.error} onRetry={() => void fresh.refetch()} />;
  } else if (!notes.length) {
    body = <EmptyState label="nothing ingested yet" hint="ingest from the inbox to fill the feed" />;
  } else {
    body = <MasonryGrid>{notes.map((item) => <FreshCard key={item.path} note={item} onOpen={(note, rect) => setSelected({ note, rect })} onDelete={handleDelete} />)}</MasonryGrid>;
  }

  return (
    <div id="fresh-page" className="hub-page">
      <HubControls>
        <SourceFilter value={source} onChange={(next) => void navigate({ search: { source: next } })} />
        <span className="count"><CountUp value={notes.length} /> recently ingested</span>
      </HubControls>
      <div className="hub-body">
        {remove.isError ? <div className="delete-error" role="alert">failed to delete note: {String(remove.error)}</div> : null}
        {body}
      </div>
      {selected ? <NoteViewer note={selected.note} originRect={selected.rect} onClose={() => setSelected(undefined)} /> : null}
      {getPref(CURSOR_PREF) ? <TargetCursor /> : null}
      {pendingDelete ? (
        <ConfirmDialog
          message="delete this note for good? it leaves the vault and the search index."
          onCancel={() => setPendingDelete(undefined)}
          onConfirm={() => {
            const item = pendingDelete;
            setPendingDelete(undefined);
            remove.mutate(item.path, { onSuccess: () => setSelected((current) => (current?.note.path === item.path ? undefined : current)) });
          }}
        />
      ) : null}
    </div>
  );
}
