/* Stepped ring gauge: fills per completed item (the backend only reports
   done/total at ~2min granularity — a smooth bar would read as stalled).
   The 180ms CSS transition on dashoffset animates each step. */
const R = 8;
const CIRC = 2 * Math.PI * R;

export function IngestRing({
  done,
  total,
  running,
}: {
  done: number;
  total: number;
  running: boolean;
}) {
  const fraction = total > 0 ? done / total : 0;
  return (
    <svg
      className={`ingest-ring${running ? " running" : ""}`}
      viewBox="0 0 20 20"
      width="20"
      height="20"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done}
      aria-label={`ingest progress: ${done} of ${total}`}
    >
      <circle
        cx="10"
        cy="10"
        r={R}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        opacity="0.18"
      />
      <circle
        className="ingest-ring-fill"
        cx="10"
        cy="10"
        r={R}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={CIRC}
        style={{ strokeDashoffset: CIRC * (1 - fraction) }}
        transform="rotate(-90 10 10)"
      />
    </svg>
  );
}
