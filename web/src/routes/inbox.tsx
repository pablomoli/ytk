import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQueue } from "../api/queue";
import { useAddUrls, useRefreshSources } from "../api/mutations";
import { useJobStatus } from "../api/job";
import { SourceFilter } from "../components/SourceFilter";
import { Card } from "../components/Card";
import { MasonryGrid } from "../components/MasonryGrid";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { useInfiniteWindow } from "../lib/useInfiniteWindow";
import "../styles.css";

export const Route = createFileRoute("/inbox")({
  validateSearch: (s: Record<string, unknown>): { source?: string } => ({
    source: typeof s.source === "string" ? s.source : undefined,
  }),
  component: InboxPage,
});

function InboxPage() {
  const { source } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const q = useQueue();
  const job = useJobStatus();
  const addUrls = useAddUrls();
  const refreshSources = useRefreshSources();
  const [urlsText, setUrlsText] = useState("");

  const items = useMemo(
    () => (q.data ?? []).filter((i) => !source || i.source === source),
    [q.data, source],
  );
  const { visible, sentinelRef } = useInfiniteWindow(items, 60);

  const handleSourceChange = (next?: string) => {
    void navigate({ search: { source: next } });
  };

  const handleUrlsChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setUrlsText(e.target.value);
  };

  const handleAdd = () => {
    const urls = urlsText
      .split(/[\s,]+/)
      .map((u) => u.trim())
      .filter(Boolean);
    if (!urls.length) return;
    addUrls.mutate(urls, { onSuccess: () => setUrlsText("") });
  };

  const handleRefresh = () => {
    refreshSources.mutate();
  };

  let body;
  if (q.isLoading) {
    body = (
      <MasonryGrid>
        <Skeletons count={12} />
      </MasonryGrid>
    );
  } else if (q.isError) {
    body = <ErrorState error={q.error} />;
  } else if (items.length === 0) {
    body = <EmptyState label="nothing in the inbox" />;
  } else {
    body = (
      <>
        <MasonryGrid>
          {visible.map((i) => (
            <Card key={i.url} item={i} onOpen={(x) => window.open(x.url, "_blank")} />
          ))}
        </MasonryGrid>
        <div ref={sentinelRef} className="sentinel" />
      </>
    );
  }

  return (
    <div id="inbox-page" className="hub-page">
      <header className="hub-header">
        <span className="brand">inbox</span>
        <SourceFilter value={source} onChange={handleSourceChange} />
        <span className="count">
          {items.length}
          {q.data && q.data.length !== items.length ? ` of ${q.data.length}` : ""} pending
        </span>
      </header>
      <div className="hub-body">
        <div className="addbox">
          <textarea
            value={urlsText}
            onChange={handleUrlsChange}
            placeholder="paste urls to add..."
            rows={2}
          />
          <div className="addbox-actions">
            <button className="btn primary" onClick={handleAdd} disabled={addUrls.isPending}>
              add
            </button>
            <button className="btn" onClick={handleRefresh} disabled={refreshSources.isPending}>
              refresh
            </button>
          </div>
          {job.data ? (
            <div className={`progress${job.data.running ? " running" : ""}`}>
              {job.data.running ? "running · " : ""}
              {job.data.done}/{job.data.total}
            </div>
          ) : null}
        </div>
        {body}
      </div>
    </div>
  );
}
