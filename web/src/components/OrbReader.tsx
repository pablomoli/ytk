import { useEffect, useRef, useState } from "react";
import type { OrbPoint } from "../api/orb";
import { useNearbyNotes, useNote, useSimilarNotes } from "../api/fresh";
import { copyAskPrompt } from "../lib/askPrompt";
import { DUR, gsap, reducedMotion } from "../lib/motion";
import { orbPointToFreshNote } from "../lib/orb/note";
import { NoteBody } from "./NoteViewer";

// css px the sphere's picture shifts left by half of, so the selected tile
// centers in the sky that remains; the scene reads it through setDock
export const READER_WIDTH = 480;

type Props = {
  point: OrbPoint;
  open: boolean; // false plays the slide-out, then onGone
  pathIndex: Map<string, number>;
  urlIndex: Map<string, number>;
  onWalk(j: number): void;
  onClose(): void;
  onGone(): void;
};

const LABEL = "text-[10.5px] uppercase tracking-[0.14em] text-[var(--ink2)]";
const ACTION =
  "cursor-pointer rounded px-2 py-1 text-[12px] text-[var(--ink2)] transition-colors hover:bg-white/[0.08] hover:text-[var(--ink)]";

/* The reading pane docked beside the sphere: the selected tile's note, then
   its text neighbors and visually similar items as steps to walk. Nothing
   here is modal; the sphere behind stays live. */
export function OrbReader({ point, open, pathIndex, urlIndex, onWalk, onClose, onGone }: Props) {
  const note = orbPointToFreshNote(point);
  const content = useNote(note.path);
  const nearby = useNearbyNotes(note.path);
  const similar = useSimilarNotes(note.path);
  const paneRef = useRef<HTMLElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [askCopied, setAskCopied] = useState(false);

  useEffect(() => {
    const el = paneRef.current;
    if (!el) return;
    if (reducedMotion()) return;
    gsap.fromTo(el, { x: READER_WIDTH }, { x: 0, duration: DUR.reveal, clearProps: "transform" });
  }, []);

  useEffect(() => {
    const el = paneRef.current;
    if (!el || open) return;
    if (reducedMotion()) { onGone(); return; }
    gsap.to(el, { x: READER_WIDTH, duration: DUR.reveal, onComplete: onGone });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // a walk swaps the note; the body fades up and scrolls back to the top
  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    el.scrollTop = 0;
    if (reducedMotion()) return;
    gsap.fromTo(el, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: DUR.morph, clearProps: "transform" });
  }, [point.p]);

  const handleAsk = async () => {
    if (await copyAskPrompt(note.path)) {
      setAskCopied(true);
      setTimeout(() => setAskCopied(false), 1500);
    }
  };

  const steps = (nearby.data?.nearby ?? []).map((n) => ({
    key: n.target,
    title: n.title,
    cosine: n.cosine,
    j: n.path !== null ? pathIndex.get(n.path) : undefined,
  }));
  const sims = (similar.data ?? []).map((s) => ({ ...s, j: s.url ? urlIndex.get(s.url) : undefined }));

  return (
    <aside
      ref={paneRef}
      className="absolute inset-y-0 right-0 flex flex-col border-l border-white/10 bg-black/80 shadow-2xl backdrop-blur-md"
      style={{ width: READER_WIDTH }}
    >
      <div className="flex flex-none items-center gap-1 border-b border-white/10 px-5 pt-3 pb-2.5">
        <span className={`${LABEL} mr-auto`}>reading</span>
        {note.url ? (
          <a className={`${ACTION} no-underline`} href={note.url} target="_blank" rel="noreferrer">
            open source
          </a>
        ) : null}
        <div role="button" tabIndex={0} className={ACTION} onClick={() => void handleAsk()}>
          {askCopied ? "copied" : "ask"}
        </div>
        <div role="button" tabIndex={0} className={ACTION} onClick={onClose} title="Escape">
          close
        </div>
      </div>
      <div ref={bodyRef} className="orb-reader min-h-0 flex-1 overflow-y-auto px-5 pb-6 text-[14px] leading-relaxed text-[var(--ink)] [scrollbar-width:thin] [&_.note-title]:!mt-4 [&_.note-title]:!text-[20px] [&_.note-title]:!leading-snug [&_.note-title]:!text-[var(--ink)] [&_.note-images_img]:!max-h-[11rem] [&_.note-images.strip_img]:!h-[11rem] [&_h3]:!text-[var(--ink2)] [&_h3]:!text-[11px] [&_h3]:!uppercase [&_h3]:!tracking-[0.14em]">
        {content.isLoading ? <p className="pt-4 text-[13px] text-[var(--ink2)]">loading note</p> : null}
        {content.isError ? <p className="pt-4 text-[13px] text-[var(--ink2)]">failed to load note</p> : null}
        {content.data ? <NoteBody raw={content.data.content} note={note} /> : null}
        {steps.length ? (
          <section className="mt-6 border-t border-white/10 pt-3">
            <div className={`${LABEL} mb-1.5`}>nearest in text</div>
            <ul className="!m-0 !list-none !p-0">
              {steps.map((s) => (
                <li key={s.key} className="!m-0 !list-none border-b border-white/[0.06] !p-0 last:border-b-0">
                  <div
                    role={s.j !== undefined ? "button" : undefined}
                    tabIndex={s.j !== undefined ? 0 : -1}
                    onClick={s.j !== undefined ? () => onWalk(s.j!) : undefined}
                    className={`flex items-baseline gap-3 py-2 ${s.j !== undefined ? "cursor-pointer hover:bg-white/[0.06]" : "opacity-50"}`}
                    title={s.j === undefined ? "not on the sphere" : undefined}
                  >
                    <span className="min-w-0 flex-1 truncate text-[13px] leading-snug text-[var(--ink)]">{s.title}</span>
                    <span className="flex-none text-[11px] tabular-nums text-[var(--accent)]">{Math.round(s.cosine * 100)}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {sims.length ? (
          <section className="mt-5">
            <div className={`${LABEL} mb-2`}>looks alike</div>
            <div className="flex flex-wrap gap-2">
              {sims.map((s) => {
                const img = (
                  <img
                    src={`/api/visual-image?id=${encodeURIComponent(s.item_id)}`}
                    loading="lazy"
                    alt=""
                    className="h-16 w-auto max-w-[7rem] rounded-[3px] object-contain"
                  />
                );
                return s.j !== undefined ? (
                  <div key={s.item_id} role="button" tabIndex={0} className="cursor-pointer opacity-90 hover:opacity-100" title={s.title ?? ""} onClick={() => onWalk(s.j!)}>
                    {img}
                  </div>
                ) : (
                  <a key={s.item_id} href={s.url || "#"} target="_blank" rel="noreferrer" title={s.title ?? ""} className="opacity-60 hover:opacity-100">
                    {img}
                  </a>
                );
              })}
            </div>
          </section>
        ) : null}
      </div>
    </aside>
  );
}
