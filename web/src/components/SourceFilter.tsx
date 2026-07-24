import { SOURCES } from "./icons";

export function SourceFilter({
  value,
  onChange,
}: {
  value?: string | undefined;
  onChange: (s?: string | undefined) => void;
}) {
  return (
    <span className="filters">
      {SOURCES.map((s) => (
        <button
          key={s}
          className={`fchip${value === s ? " on" : ""}`}
          aria-pressed={value === s}
          onClick={() => onChange(value === s ? undefined : s)}
        >
          {s}
        </button>
      ))}
    </span>
  );
}
