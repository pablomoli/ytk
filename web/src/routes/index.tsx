import { useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { FreshCard } from "../components/FreshCard";
import { MasonryGrid } from "../components/MasonryGrid";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { SourceFilter } from "../components/SourceFilter";
import { canonicalSource } from "../components/icons";
import { useDeleteNote, useFreshNotes, useNote, useSimilarNotes } from "../api/fresh";
import type { FreshNote } from "../api/fresh";
import "../styles.css";

export const Route = createFileRoute("/")({
  component: IndexPage,
});

function IndexPage() {
  const fresh = useFreshNotes();
  const remove = useDeleteNote();
  const [source, setSource] = useState<string>();
  const [selected, setSelected] = useState<FreshNote>();
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
      <header className="hub-header">
        <h1>fresh</h1>
        <SourceFilter value={source} onChange={setSource} />
        <span className="count">{notes.length} recently ingested</span>
      </header>
      <div className="hub-body">{body}</div>
      {selected ? (
        <div className="note-viewer" role="dialog" aria-modal="true" aria-label={selected.title} onClick={() => setSelected(undefined)}>
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
