import type { FreshNote } from "../../api/fresh";
import type { OrbPoint } from "../../api/orb";

/* NoteViewer's real key is note.path (useNote/useSimilarNotes); the rest of
   FreshNote is display fallback. Tags and has_take are absent from map data
   and default empty — the viewer fetches full content by path anyway. */
export function orbPointToFreshNote(p: OrbPoint): FreshNote {
  const base = p.p.split("/").pop() ?? p.p;
  return {
    path: p.p,
    stem: base.replace(/\.md$/, ""),
    title: p.t,
    url: p.u ?? null,
    source: p.c,
    date: p.d ?? null,
    added: p.d ?? "",
    thumbnail: p.thumb ?? null,
    tags: [],
    has_take: false,
  };
}
