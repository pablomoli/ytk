import { SOURCES, sourceIcon } from "./icons";
import { cn } from "../lib/utils";

// Single-select source filter: same icon-tile vocabulary as the inbox's
// SourceSelect, one source at a time.
export function SourceFilter({
  value,
  onChange,
}: {
  // The property needs the explicit `| undefined` under
  // exactOptionalPropertyTypes; the callback parameter does not.
  value?: string | undefined;
  onChange: (s?: string) => void;
}) {
  return (
    <span className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by source">
      {SOURCES.map((s) => (
        <button
          key={s}
          type="button"
          className={cn("source-option size-9", value === s && "on")}
          aria-pressed={value === s}
          title={s}
          onClick={() => onChange(value === s ? undefined : s)}
        >
          {sourceIcon(s, 18)}
          <span className="source-option-label">{s}</span>
        </button>
      ))}
    </span>
  );
}
