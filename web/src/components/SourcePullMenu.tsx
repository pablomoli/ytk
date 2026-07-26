import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { PULL_SOURCES } from "./icons";

type Anchor = { left: number; top: number; flipped: boolean };

const MENU_W = 200;
const GAP = 6;

/* Where the popover goes, given the caret's rect. Opens downward normally and
   flips above the caret when there is not enough room below, so the confirm
   button is always on screen. Pure, so the placement is testable without a
   layout. */
export function anchorFor(
  caret: { left: number; right: number; top: number; bottom: number },
  menuHeight: number,
  viewport: { width: number; height: number },
  gap = GAP,
  menuWidth = MENU_W,
): Anchor {
  const roomBelow = viewport.height - caret.bottom;
  const flipped = roomBelow < menuHeight + gap && caret.top > roomBelow;
  const top = flipped ? Math.max(gap, caret.top - menuHeight - gap) : caret.bottom + gap;
  /* Right-aligned to the caret, then pulled back inside the viewport rather
     than allowed to run off either edge. */
  const left = Math.min(Math.max(gap, caret.right - menuWidth), viewport.width - menuWidth - gap);
  return { left, top, flipped };
}

/* A popover next to the "refresh" button for pulling only chosen sources.
   The plain refresh still pulls everything; this is the "just check Instagram
   right now" path. Selection is local state — nothing to persist for a one-off
   action.

   Rendered through a portal with fixed positioning, NOT as an absolutely
   positioned child. The rail clips its overflow and .rail-scroll scrolls, so a
   child popover is cut off at the container edge: once #126 added a widget
   above this one, the caret sat far enough down the rail that the confirm
   button landed 94px below the fold at a 1440x800 window and could not be
   clicked at all. The same failure as #125's stranded ingest button. A portal
   is the only fix that does not depend on how much sits above it. */
export function SourcePullMenu({
  onPull,
  disabled,
}: {
  onPull: (only: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  /* Measured after paint, because the flip decision needs the menu's real
     height — guessing it puts the popover in the wrong place on first open. */
  useLayoutEffect(() => {
    if (!open) {
      setAnchor(null);
      return;
    }
    const caret = ref.current?.getBoundingClientRect();
    if (!caret) return;
    const height = menuRef.current?.getBoundingClientRect().height ?? 0;
    setAnchor(anchorFor(caret, height, { width: window.innerWidth, height: window.innerHeight }));
  }, [open]);

  // Close on outside click / Escape, the usual popover dismissal.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      /* The menu is portaled out of `ref`, so it has to be checked separately —
         otherwise every click inside the menu reads as an outside click and
         dismisses it before it can do anything. */
      if (ref.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    /* Fixed coordinates go stale the moment anything moves under them. */
    const onReflow = () => setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onReflow);
    window.addEventListener("scroll", onReflow, true);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onReflow);
      window.removeEventListener("scroll", onReflow, true);
    };
  }, [open]);

  const toggle = (s: string) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });

  const pull = () => {
    if (chosen.size === 0) return;
    onPull([...chosen]);
    setOpen(false);
  };

  const menu = (
    <div
      className="source-pull-menu"
      role="menu"
      ref={menuRef}
      style={
        anchor ? { left: `${anchor.left}px`, top: `${anchor.top}px` } : { visibility: "hidden" }
      }
    >
      <div className="source-pull-head">pull only</div>
      {PULL_SOURCES.map((s) => (
        <label key={s} className="source-pull-row">
          <input type="checkbox" checked={chosen.has(s)} onChange={() => toggle(s)} />
          {s}
        </label>
      ))}
      <button className="btn primary" onClick={pull} disabled={chosen.size === 0}>
        pull {chosen.size > 0 ? `(${chosen.size})` : ""}
      </button>
    </div>
  );

  return (
    <div className="source-pull" ref={ref}>
      <button
        className="btn caret"
        aria-label="pull specific sources"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        &#9662;
      </button>
      {open ? createPortal(menu, document.body) : null}
    </div>
  );
}
