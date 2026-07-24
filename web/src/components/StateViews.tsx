import { ApiError } from "../api/client";

/* Quiet observatory glyph: a hairline circle with a centered dot. */
const Glyph = () => (
  <svg className="state-glyph" viewBox="0 0 48 48" width="48" height="48" aria-hidden="true">
    <circle
      cx="24"
      cy="24"
      r="21"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      opacity="0.35"
    />
    <circle cx="24" cy="24" r="3" fill="currentColor" opacity="0.7" />
  </svg>
);

export const EmptyState = ({ label, hint }: { label: string; hint?: string | undefined }) => (
  <div className="empty state-view">
    <Glyph />
    <p className="state-title">{label}</p>
    {hint ? <p className="state-hint">{hint}</p> : null}
  </div>
);

export const ErrorState = ({ error, onRetry }: { error: unknown; onRetry?: () => void }) => {
  const detail =
    error instanceof ApiError &&
    typeof error.body === "object" &&
    error.body &&
    "detail" in error.body
      ? String(error.body.detail)
      : String(error);
  return (
    <div className="empty state-view">
      <Glyph />
      <p className="state-title">failed to load</p>
      <p className="state-hint">{detail}</p>
      {onRetry ? (
        <button className="btn" type="button" onClick={onRetry}>
          retry
        </button>
      ) : null}
    </div>
  );
};
