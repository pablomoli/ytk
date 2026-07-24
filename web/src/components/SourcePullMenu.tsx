import { useEffect, useRef, useState } from "react";
import { PULL_SOURCES } from "./icons";

/* A popover next to the "refresh" button for pulling only chosen sources.
   The plain refresh still pulls everything; this is the "just check Instagram
   right now" path. Selection is local state — nothing to persist for a one-off
   action. */
export function SourcePullMenu({
  onPull,
  disabled,
}: {
  onPull: (only: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape, the usual popover dismissal.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
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
      {open ? (
        <div className="source-pull-menu" role="menu">
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
      ) : null}
    </div>
  );
}
