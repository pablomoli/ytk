import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { getPref, setPref } from "../lib/prefs";

/* One collapsible section of the inbox rail. Native details/summary carries
   the keyboard and screen-reader semantics, so there is no ARIA to maintain
   here. Open state persists per widget, which is why each caller passes its
   own pref key.

   The element owns its own open attribute; React never re-renders it. Driving
   it from state instead puts React and the browser's default action on the
   same attribute, and they cancel: the first click appears to do nothing and
   the section only responds to the second. The initial value is read once and
   held constant, so React writes it on mount and never touches it again. */
export function RailWidget({
  title,
  prefKey,
  defaultOpen = false,
  forceOpenKey,
  meta,
  children,
}: {
  title: string;
  prefKey: string;
  defaultOpen?: boolean;
  forceOpenKey?: string | number | null;
  meta?: ReactNode;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDetailsElement>(null);
  const initialOpen = useRef(getPref(prefKey, defaultOpen)).current;
  /* Opens once per new key, then leaves the user alone: a job that is still
     running must not re-open a section the user deliberately closed. Starts
     at null, not forceOpenKey's initial value, so mounting with a key already
     set (a job already running when the widget appears) still counts as a
     change and opens it. */
  const forced = useRef<string | number | null>(null);

  useEffect(() => {
    const key = forceOpenKey ?? null;
    if (key === null) {
      /* Job ended: clear the guard so the next job, even one that lands on
         the same key (JobStatus carries no id, and item count repeats across
         runs), is still seen as a change and reopens the section. */
      forced.current = null;
      return;
    }
    if (key === forced.current) return;
    forced.current = key;
    if (ref.current) ref.current.open = true;
    setPref(prefKey, true);
  }, [forceOpenKey, prefKey]);

  /* Fires for every way the attribute can change - pointer, Enter, Space,
     find-in-page auto-expand - so the stored preference follows all of them. */
  const persist = (event: React.SyntheticEvent<HTMLDetailsElement>) => {
    setPref(prefKey, event.currentTarget.open);
  };

  return (
    <details className="rail-widget" ref={ref} open={initialOpen} onToggle={persist}>
      <summary>
        <h2>{title}</h2>
        {meta ? <span className="count float-right">{meta}</span> : null}
      </summary>
      {children}
    </details>
  );
}
