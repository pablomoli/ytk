import { SOURCES, canonicalSource, sourceIcon } from "./icons";
import type { SourceSelection } from "../lib/sourceFilter";
import { allSources, materializeSources } from "../lib/sourceFilter";

/* Multi-select source filter for the inbox (#126).

   The inbox used SourceFilter — action chips with aria-pressed, one selectable
   at a time, mounted in the global header. That is the wrong vocabulary twice
   over: this is a page-local preference, not a global action, and it is
   multi-valued, so it is a named group of checkboxes living in the inbox rail.

   SourceFilter is left alone rather than migrated, because /library and / still
   use it for genuinely single-valued filtering. #126 is inbox-scoped; folding
   those in is a separate change. */
export function SourceSelect({
  selection,
  onChange,
}: {
  selection: SourceSelection;
  onChange: (next: SourceSelection) => void;
}) {
  const active = materializeSources(selection, SOURCES);
  const everything = allSources(SOURCES);

  const toggle = (source: string) => {
    const next = new Set(active);
    const name = canonicalSource(source);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(next);
  };

  return (
    <div className="source-select">
      <div className="source-select-list" role="group" aria-label="Filter by source">
        {SOURCES.map((s) => {
          const checked = active.has(canonicalSource(s));
          return (
            <label key={s} className={`source-option${checked ? " on" : ""}`}>
              <input type="checkbox" checked={checked} onChange={() => toggle(s)} />
              {sourceIcon(s)}
              <span>{s}</span>
            </label>
          );
        })}
      </div>
      <div className="source-select-actions">
        <button
          className="btn"
          type="button"
          onClick={() => onChange(everything)}
          disabled={active.size === everything.size}
        >
          all sources
        </button>
        <button
          className="btn"
          type="button"
          onClick={() => onChange(null)}
          /* Back to the default, which is not "select everything": it re-hides
             the sources excluded by policy. */
          disabled={selection === null}
        >
          defaults
        </button>
      </div>
    </div>
  );
}
