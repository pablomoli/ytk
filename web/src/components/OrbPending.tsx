import { useEffect, useRef } from "react";
import { DUR, gsap, reducedMotion } from "../lib/motion";
import type { RingItem } from "../lib/orb/ring";
import { WORD, word } from "./OrbControls";
import { READER_WIDTH } from "./OrbReader";

export type PendingRow = { title: string; text: string; author: string; source: string; shared_at: string; question: string };
export type PendingDetail = { row: PendingRow | null; hits: { i: number; s: number }[] };

type Props = {
  item: RingItem;
  detail: PendingDetail | undefined; // undefined while the row is on its way
  beside: { title: string; score: number }[]; // the tiles its words sit nearest, the seat's evidence
  left: number; // pending items not yet kept or dropped
  open: boolean; // false plays the slide-out, then onGone
  busy: boolean; // a grain is in the air
  canKeep: boolean;
  onKeep: () => void;
  onDrop: () => void;
  onStep: (by: 1 | -1) => void;
  onClose: () => void;
  onGone: () => void;
};

const SMALL = "text-[13px]";
const day = (d: string) => {
  const t = d ? new Date(`${d.slice(0, 10)}T12:00:00`) : null;
  return t && !Number.isNaN(t.getTime()) ? t.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }) : "";
};
// only the host is shown: a saved link can carry a token in its path
const host = (u: string) => {
  try { return /^https?:/.test(u) ? new URL(u).host.replace(/^www\./, "") : ""; } catch { return ""; }
};

/* A pending item read beside the sphere, in the place a note is read: what the
   queue holds for it, where it would sit, and the two things to do with it.
   A rehearsal: keep and drop move the grain and write nothing. */
export function OrbPending({ item, detail, beside, left, open, busy, canKeep, onKeep, onDrop, onStep, onClose, onGone }: Props) {
  const paneRef = useRef<HTMLElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = paneRef.current;
    if (!el || reducedMotion()) return;
    gsap.fromTo(el, { x: READER_WIDTH }, { x: 0, duration: DUR.reveal, clearProps: "transform" });
  }, []);

  useEffect(() => {
    const el = paneRef.current;
    if (!el || open) return;
    if (reducedMotion()) { onGone(); return; }
    gsap.to(el, { x: READER_WIDTH, duration: DUR.reveal, onComplete: onGone });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // a step swaps the item; the body fades up and scrolls back to the top
  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    el.scrollTop = 0;
    if (reducedMotion()) return;
    gsap.fromTo(el, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: DUR.morph, clearProps: "transform" });
  }, [item.u]);

  const row = detail?.row;
  // some sources file a whole caption as the title; past a line or two it is set as the text it is
  const named = (row?.title ?? "").trim();
  const title = named.length <= 100 ? named : "";
  const text = ((row ? row.text : item.t).trim() || (title ? "" : named)).trim();
  const author = row?.author || item.a;
  const source = row?.source || item.s;
  const saved = day(row?.shared_at || item.d);
  const question = row ? row.question : "";
  const link = host(item.u);
  const from = [author ? `from ${author}` : "", source ? `on ${source}` : "", saved ? `saved ${saved}` : ""].filter(Boolean).join(", ");

  return (
    <aside
      ref={paneRef}
      data-orb-pending
      className="absolute inset-y-0 right-0 flex flex-col border-l border-white/10 bg-black/80 font-[540] tracking-[-0.015em] text-ink shadow-2xl backdrop-blur-md"
      style={{ width: READER_WIDTH }}
    >
      <div className={`${SMALL} flex flex-none items-baseline gap-4 border-b border-white/10 px-5 pt-3.5 pb-3 leading-none`}>
        <span className="mr-auto italic text-ink2">
          pending <span className="not-italic text-[0.82em] tabular-nums text-accent">{left}</span>
        </span>
        <button type="button" data-orb-pending-step="-1" className={word(false)} disabled={busy} onClick={() => onStep(-1)} title="left arrow">
          previous
        </button>
        <button type="button" data-orb-pending-step="1" className={word(false)} disabled={busy} onClick={() => onStep(1)} title="right arrow">
          next
        </button>
        <button type="button" className={word(false)} onClick={onClose} title="Escape">
          close
        </button>
      </div>
      <div ref={bodyRef} className="min-h-0 flex-1 overflow-y-auto px-5 pt-5 pb-6 [scrollbar-width:thin]">
        {/* only cached covers: asking for an uncached one makes the hub download it */}
        {item.k >= 0 ? (
          <img src={`/api/cover?u=${encodeURIComponent(item.u)}`} alt="" className="mb-5 block max-h-[17rem] max-w-full rounded-[3px] object-contain" />
        ) : null}
        {/* a paragraph: the hub's own heading rules would repaint an h2 */}
        {title ? <p className="!m-0 text-[23px] leading-[1.12] text-ink">{title}</p> : null}
        {from ? <p className={`${SMALL} !m-0 ${title ? "!mt-2" : ""} leading-snug text-ink2`}>{from}</p> : null}
        {text && text !== title ? (
          <p className={`!m-0 !mt-4 whitespace-pre-line break-words font-normal ${title ? "text-[14px] leading-relaxed text-ink/90" : "text-[16px] leading-[1.5] text-ink"}`}>{text}</p>
        ) : null}
        {!title && !text ? (
          <p className="!m-0 !mt-4 text-[14px] italic leading-relaxed text-ink2">The queue holds no words for this one, only where it came from.</p>
        ) : null}
        {question ? <p className="!m-0 !mt-5 text-[17px] italic leading-snug text-accent">{question}</p> : null}
        {beside.length ? (
          <section className="mt-7 border-t border-white/10 pt-3.5">
            <p className={`${SMALL} !m-0 italic text-ink2`}>would sit beside</p>
            <ul className="!m-0 !mt-1.5 !list-none !p-0">
              {beside.map((b) => (
                <li key={b.title} className="!m-0 flex !list-none items-baseline gap-3 !p-0 py-[5px]">
                  <span className="min-w-0 flex-1 truncate text-[14px] leading-snug">{b.title}</span>
                  <span className="flex-none text-[11px] tabular-nums text-accent">{Math.round(b.score * 100)}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : detail && !canKeep ? (
          <p className={`${SMALL} !m-0 !mt-7 border-t border-white/10 pt-3.5 italic leading-snug text-ink2`}>
            Nothing to seat it by yet. Keeping it for real would fetch it first, and its seat would follow from what it says.
          </p>
        ) : null}
      </div>
      <div className="flex-none border-t border-white/10 px-5 pt-4 pb-4">
        <div className="flex items-baseline gap-7 text-[26px] leading-none">
          <button
            type="button"
            data-orb-pending-keep
            disabled={busy || !canKeep}
            title={canKeep ? "send it to its seat on the sphere (k)" : "nothing to seat it by yet"}
            className={`${WORD} border-b-[1.5px] pb-1 ${canKeep ? "!border-accent text-ink" : "!border-transparent cursor-default text-ink2/35"}`}
            onClick={onKeep}
          >
            keep
          </button>
          <button type="button" data-orb-pending-drop disabled={busy} title="let it fall away (d)" className={`${word(false)} pb-1`} onClick={onDrop}>
            drop
          </button>
          {link ? (
            <a className={`${SMALL} ml-auto text-ink2/60 no-underline transition-colors duration-200 hover:text-ink`} href={item.u} target="_blank" rel="noreferrer">
              open on {link}
            </a>
          ) : null}
        </div>
        <p className="!m-0 !mt-3 text-[12px] italic leading-snug text-ink2/60">A rehearsal: nothing is written, and a reload puts every item back.</p>
      </div>
    </aside>
  );
}
