import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { getPref, setPref } from "../lib/prefs";

/* One collapsible section of the inbox rail. Native details/summary carries
   the keyboard and screen-reader semantics, so there is no ARIA to maintain
   here. Open state persists per widget, which is why each caller passes its
   own pref key. */
export function RailWidget({
  title,
  prefKey,
  defaultOpen = false,
  forceOpenKey,
  children,
}: {
  title: string;
  prefKey: string;
  defaultOpen?: boolean;
  forceOpenKey?: string | number | null;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(() => getPref(prefKey, defaultOpen));
  /* Opens once per new key, then leaves the user alone: a job that is still
     running must not re-open a section the user deliberately closed. Starts
     at null, not forceOpenKey's initial value, so mounting with a key
     already set (a job already running when the widget appears) still
     counts as a change and opens it. */
  const forced = useRef<string | number | null>(null);

  useEffect(() => {
    const key = forceOpenKey ?? null;
    if (key === null) {
      /* Job ended: clear the guard so the next job, even one that lands on
         the same key (JobStatus carries no id, and item count repeats
         across runs), is still seen as a change and reopens the section. */
      forced.current = null;
      return;
    }
    if (key === forced.current) return;
    forced.current = key;
    setOpen(true);
    setPref(prefKey, true);
  }, [forceOpenKey, prefKey]);

  /* The native toggle event fires asynchronously (queued as a task per the
     HTML spec, not synchronously with the click that caused it), so an
     onToggle handler leaves the persisted pref stale for a tick. Clicking
     summary is itself synchronous, and its default action of flipping the
     details' open attribute is left alone here, so persist against that
     same click rather than waiting on the event it triggers. */
  const toggle = () => {
    const next = !open;
    setOpen(next);
    setPref(prefKey, next);
  };

  return (
    <details className="rail-widget" open={open}>
      <summary onClick={toggle}>
        <h2>{title}</h2>
      </summary>
      {children}
    </details>
  );
}
