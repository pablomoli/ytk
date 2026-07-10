const SOURCES = ['instagram', 'youtube', 'pinterest', 'tiktok', 'web', 'memo']

export function SourceFilter({ value, onChange }: { value?: string; onChange: (s?: string) => void }) {
  return (
    <span className="filters">
      {SOURCES.map(s => (
        <button
          key={s}
          className={`fchip${value === s ? ' on' : ''}`}
          onClick={() => onChange(value === s ? undefined : s)}
        >
          {s}
        </button>
      ))}
    </span>
  )
}
