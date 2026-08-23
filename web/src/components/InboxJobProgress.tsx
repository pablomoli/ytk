import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import type { JobStatus } from "../api/job";
import { IngestRing } from "./IngestRing";

export function InboxJobProgress({
  job,
  currentTitle = "",
  elapsed = "",
}: {
  job?: JobStatus | undefined;
  currentTitle?: string;
  elapsed?: string;
}) {
  if (!job || (!job.running && job.total <= 0)) return null;

  const total = Math.max(job.total, 0);
  const done = Math.max(job.done, 0);
  const remaining = Math.max(total - done, 0);
  const failed = Math.min(job.failures.length, total);
  const succeeded = Math.max(Math.min(done, total) - failed, 0);
  const liveText = job.running
    ? `Ingest running. ${remaining} ${remaining === 1 ? "item" : "items"} remaining.`
    : failed > 0
      ? `Ingest complete with failures. ${succeeded} succeeded, ${failed} failed.`
      : `Ingest complete. ${succeeded} succeeded.`;

  return (
    <section
      aria-label="Ingest job progress"
      className="flex-none rounded-lg border border-line bg-bg2 p-3 font-data"
      data-testid="inbox-job-progress"
    >
      <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {liveText}
      </span>
      <div className="flex items-start gap-2.5">
        {job.running ? (
          <IngestRing done={done} total={total} running />
        ) : failed > 0 ? (
          <WarningCircle className="size-5 shrink-0 text-amber-300" aria-hidden="true" />
        ) : (
          <CheckCircle className="size-5 shrink-0 text-live" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          {job.running ? (
            <p className="m-0 text-sm font-semibold text-ink">
              {remaining} {remaining === 1 ? "item" : "items"} remaining
            </p>
          ) : failed > 0 ? (
            <div className="flex flex-wrap gap-x-2 gap-y-1 text-sm">
              <span className="font-semibold text-ink">{succeeded} ingested</span>
              <span className="text-amber-300">{failed} failed</span>
            </div>
          ) : (
            <p className="m-0 text-sm font-semibold text-ink">
              {succeeded} {succeeded === 1 ? "item" : "items"} ingested
            </p>
          )}
          {job.running && (currentTitle || elapsed) ? (
            <p className="mt-1 mb-0 flex min-w-0 flex-wrap gap-x-2 gap-y-0.5 text-xs leading-snug text-ink2">
              {currentTitle ? <span className="min-w-0 break-words">{currentTitle}</span> : null}
              {elapsed ? (
                <span className="shrink-0 text-mute tabular-nums" aria-hidden="true">
                  {elapsed} elapsed
                </span>
              ) : null}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
