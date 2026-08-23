import { useRef } from "react";
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
  meta,
  children,
}: {
  title: string;
  prefKey: string;
  defaultOpen?: boolean;
  meta?: ReactNode;
  children: ReactNode;
}) {
  const initialOpen = useRef(getPref(prefKey, defaultOpen)).current;

  /* Fires for every way the attribute can change - pointer, Enter, Space,
     find-in-page auto-expand - so the stored preference follows all of them. */
  const persist = (event: React.SyntheticEvent<HTMLDetailsElement>) => {
    setPref(prefKey, event.currentTarget.open);
  };

  return (
    <details className="rail-widget" open={initialOpen} onToggle={persist}>
      <summary>
        <h2>{title}</h2>
        {meta ? <span className="count float-right">{meta}</span> : null}
      </summary>
      {children}
    </details>
  );
}
