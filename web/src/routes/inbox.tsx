import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useQueue } from "../api/queue";
import type { QueueItem } from "../api/queue";
import { useAddUrls, useRefreshSources, useIngest } from "../api/mutations";
import { useJobStatus } from "../api/job";
import { apiGet } from "../api/client";
import { SourceFilter } from "../components/SourceFilter";
import { Card } from "../components/Card";
import { MasonryGrid } from "../components/MasonryGrid";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { HubControls } from "../components/HubControls";
import { useInfiniteWindow } from "../lib/useInfiniteWindow";
import { filterAndSortQueue } from "../lib/queueItems";
import "../styles.css";

export const Route = createFileRoute("/inbox")({
  validateSearch: (s: Record<string, unknown>): { source?: string } => ({
    source: typeof s.source === "string" ? s.source : undefined,
  }),
  component: InboxPage,
});

const fetchTags = () => apiGet<{ tags: string[] }>("/api/tags").then((r) => r.tags);

function InboxPage() {
  const { source } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const q = useQueue();
  const job = useJobStatus();
  const addUrls = useAddUrls();
  const refreshSources = useRefreshSources();
  const ingest = useIngest();
  const tags = useQuery({ queryKey: ["tags"], queryFn: fetchTags });

  const [urlsText, setUrlsText] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [chosenTags, setChosenTags] = useState<Set<string>>(new Set());
  const [thought, setThought] = useState("");

  const items = useMemo(
    () => filterAndSortQueue(q.data ?? [], source),
    [q.data, source],
  );
  // Progressively renders more of `items` as the sentinel scrolls into view;
  // not a bounded/sliding window, the visible count only grows.
  const { visible, sentinelRef } = useInfiniteWindow(items, 60);

  // The in-flight item, named. A batch runs ~2 minutes per video, so a bare
  // "0/3" sits unchanged long enough to read as broken; showing which video is
  // being worked, and for how long, is the difference between stalled and slow.
  const currentTitle = useMemo(() => {
    const url = job.data?.current;
    if (!url) return "";
    const item = (q.data ?? []).find((i) => i.url === url);
    return item?.text || item?.author || url;
  }, [q.data, job.data?.current]);

  // job.data refreshes every second while running, which re-renders this.
  const elapsed = useMemo(() => {
    const startedAt = job.data?.current_started;
    if (!startedAt) return "";
    const secs = Math.max(0, Math.floor(Date.now() / 1000 - startedAt));
    return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
  }, [job.data?.current_started, job.data?.done, job.dataUpdatedAt]);

  const cardState = (item: QueueItem): "queued" | "ingesting" | undefined => {
    if (job.data?.current === item.url) return "ingesting";
    if (job.data?.queued.includes(item.url)) return "queued";
    return undefined;
  };

  const handleToggleSelect = (item: QueueItem) => {
    const state = cardState(item);
    if (state === "queued" || state === "ingesting") return;
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(item.url)) {
        next.delete(item.url);
      } else {
        next.add(item.url);
      }
      return next;
    });
  };

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

  const handleToggleTag = (t: string) => {
    setChosenTags((prev) => {
      const next = new Set(prev);
      if (next.has(t)) {
        next.delete(t);
      } else {
        next.add(t);
      }
      return next;
    });
  };

  const handleThoughtChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setThought(e.target.value);
  };

  const handleIngest = () => {
    if (sel.size === 0) return;
    ingest.mutate(
      { urls: [...sel], tags: [...chosenTags], thought },
      {
        onSuccess: () => {
          setSel(new Set());
          setThought("");
        },
      },
    );
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
            <Card
              key={i.url}
              item={i}
              onOpen={handleToggleSelect}
              selected={sel.has(i.url)}
              state={cardState(i)}
            />
          ))}
        </MasonryGrid>
        <div ref={sentinelRef} className="sentinel" />
      </>
    );
  }

  return (
    <div id="inbox-page" className="hub-page">
      <HubControls>
        <SourceFilter value={source} onChange={handleSourceChange} />
        <span className="count">
          {items.length}
          {q.data && q.data.length !== items.length ? ` of ${q.data.length}` : ""} pending
        </span>
      </HubControls>
      <div className="hub-body hub-row">
        <div className="grid-col">{body}</div>
        <aside className="rail">
          <h2>add to queue</h2>
          <textarea
            className="addurls"
            aria-label="URLs to add to the queue"
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

          <h2>ingest</h2>
          <span className="selcount">{sel.size} selected</span>
          <div className="chips">
            {(tags.data ?? []).map((t) => (
              <button
                key={t}
                className={`chip${chosenTags.has(t) ? " on" : ""}`}
                onClick={() => handleToggleTag(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <textarea
            className="thought"
            aria-label="Thought to add to selected items"
            value={thought}
            onChange={handleThoughtChange}
            placeholder="thought (optional)"
          />
          <button
            className="btn primary"
            onClick={handleIngest}
            disabled={sel.size === 0 || ingest.isPending}
          >
            ingest
          </button>

          {job.data && (job.data.running || job.data.total > 0) ? (
            <div className={`progress${job.data.running ? " running" : ""}`}>
              <span className="progress-line">
                {job.data.running ? (
                  <span className="ingest-spinner" aria-hidden="true" />
                ) : null}
                <span>
                  {job.data.running ? "running · " : "done · "}
                  {job.data.done}/{job.data.total}
                  {job.data.running && elapsed ? ` · ${elapsed}` : ""}
                </span>
              </span>
              {job.data.running ? (
                <>
                  <span className="progress-current" title={currentTitle}>
                    {currentTitle}
                  </span>
                  <span className="progress-hint">enrichment takes ~2 min per item</span>
                </>
              ) : null}
              {job.data.failures.length > 0 ? (
                <span className="progress-failed">
                  {job.data.failures.length} failed
                </span>
              ) : null}
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
