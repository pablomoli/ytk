import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useQueue } from "../api/queue";
import type { QueueItem } from "../api/queue";
import { useAddUrls, useRefreshSources, useIngest } from "../api/mutations";
import { useJobStatus } from "../api/job";
import { useProfileRank, useStartProfileRank } from "../api/profileRank";
import { apiGet } from "../api/client";
import { QueueItemViewer } from "../components/QueueItemViewer";
import { SourceFilter } from "../components/SourceFilter";
import { SourcePullMenu } from "../components/SourcePullMenu";
import { Card } from "../components/Card";
import { MasonryGrid } from "../components/MasonryGrid";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { HubControls } from "../components/HubControls";
import { CountUp } from "../components/CountUp";
import { IngestRing } from "../components/IngestRing";
import { ScrambleStatus } from "../components/ScrambleStatus";
import { RailWidget } from "../components/RailWidget";
import { useInfiniteWindow } from "../lib/useInfiniteWindow";
import { filterAndSortQueue } from "../lib/queueItems";
import { formatElapsed } from "../lib/elapsed";
import {
  PROFILE_MATCHES_PREF,
  RAIL_QUEUE_PREF,
  RAIL_MATCH_PREF,
  RAIL_INGEST_PREF,
  RAIL_JOB_PREF,
  getPref,
  setPref,
} from "../lib/prefs";
import "../styles.css";

export const Route = createFileRoute("/inbox")({
  validateSearch: (s: Record<string, unknown>): { source?: string | undefined } => ({
    source: typeof s.source === "string" ? s.source : undefined,
  }),
  component: InboxPage,
});

const fetchTags = () => apiGet<{ tags: string[] }>("/api/tags").then((r) => r.tags);

// Must match the backend's page_size (rank_all_pending), so one UI batch equals
// one stratified block of the ranked pool.
const PROFILE_BATCH_SIZE = 30;

function InboxPage() {
  const { source } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const q = useQueue();
  const job = useJobStatus();
  const addUrls = useAddUrls();
  const refreshSources = useRefreshSources();
  const ingest = useIngest();
  const tags = useQuery({ queryKey: ["tags"], queryFn: fetchTags });
  const profileRank = useProfileRank();
  const startProfileRank = useStartProfileRank();

  const [urlsText, setUrlsText] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  /* Inspection is state of its own, not a mode of selection: opening the viewer
     must leave the selection exactly as it was (#123). */
  const [inspecting, setInspecting] = useState<QueueItem | null>(null);
  const [chosenTags, setChosenTags] = useState<Set<string>>(new Set());
  const [thought, setThought] = useState("");
  const [batch, setBatch] = useState(0);
  // Off by default: a cached ranking stays quiet until asked for. Persisted so
  // the choice sticks across visits (getPref reads localStorage).
  const [showMatches, setShowMatches] = useState(() => getPref(PROFILE_MATCHES_PREF));
  const setShowMatchesPref = (on: boolean) => {
    setShowMatches(on);
    setPref(PROFILE_MATCHES_PREF, on);
  };
  const handleRankByProfile = () => {
    setShowMatchesPref(true); // you asked to rank, so surface the result
    startProfileRank.mutate();
  };

  // The backend ranks the whole scorable pool into stratified blocks of
  // PROFILE_BATCH_SIZE; the inbox highlights one block at a time. "reroll"
  // advances a block (wrapping at the end), "reset" returns to the first.
  // Paging is pure slicing of the already-fetched list — no re-scoring.
  // Memoised for the same reason as recs.tsx: the ?? [] fallback otherwise
  // returns a new array identity every render and batchPicks never memoises.
  const allPicks = useMemo(() => profileRank.data?.picks ?? [], [profileRank.data?.picks]);
  const batchCount = Math.max(1, Math.ceil(allPicks.length / PROFILE_BATCH_SIZE));
  const generatedAt = profileRank.data?.generated_at;
  useEffect(() => setBatch(0), [generatedAt]); // a fresh ranking starts at batch 1
  const activeBatch = Math.min(batch, batchCount - 1);
  const batchPicks = useMemo(
    () => allPicks.slice(activeBatch * PROFILE_BATCH_SIZE, (activeBatch + 1) * PROFILE_BATCH_SIZE),
    [allPicks, activeBatch],
  );
  // When the toggle is off this resolves to an empty map, so promotion to the
  // top of the grid and the per-card badge prop both fall away at one gate.
  const matchByUrl = useMemo(
    () => (showMatches ? new Map(batchPicks.map((pick) => [pick.url, pick])) : new Map()),
    [batchPicks, showMatches],
  );
  const items = useMemo(() => {
    const filtered = filterAndSortQueue(q.data ?? [], source);
    if (matchByUrl.size === 0) return filtered;
    // Matched picks lead the inbox; both groups keep filtered's newest-first
    // order, so the freshest item leads within the highlighted set. Unscored
    // items are never hidden — they just follow the matches.
    const matched = filtered.filter((i) => matchByUrl.has(i.url));
    const rest = filtered.filter((i) => !matchByUrl.has(i.url));
    return [...matched, ...rest];
  }, [q.data, source, matchByUrl]);
  const activeHighlightCount = useMemo(
    () => items.filter((item) => matchByUrl.has(item.url)).length,
    [items, matchByUrl],
  );
  // Progressively renders more of `items` as the sentinel scrolls into view;
  // not a bounded/sliding window, the visible count only grows.
  const { visible, sentinelRef } = useInfiniteWindow(items, 60, source ?? "");

  // The in-flight item, named. A batch runs ~2 minutes per video, so a bare
  // "0/3" sits unchanged long enough to read as broken; showing which video is
  // being worked, and for how long, is the difference between stalled and slow.
  const currentTitle = useMemo(() => {
    const url = job.data?.current;
    if (!url) return "";
    const item = (q.data ?? []).find((i) => i.url === url);
    return item?.text || item?.author || url;
  }, [q.data, job.data?.current]);

  // A real 1s clock: the memo version stopped ticking whenever job polling
  // paused, freezing the elapsed readout mid-run.
  const [nowSec, setNowSec] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    if (!job.data?.running) return;
    const id = setInterval(() => setNowSec(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(id);
  }, [job.data?.running]);
  const elapsed = useMemo(
    () => formatElapsed(nowSec, job.data?.current_started),
    [job.data?.current_started, nowSec],
  );

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
    refreshSources.mutate(undefined); // plain refresh: all sources, cadence-respecting
  };

  const handleSelectivePull = (only: string[]) => {
    refreshSources.mutate({ only, force: true });
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
    body = <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  } else if (items.length === 0) {
    body = <EmptyState label="nothing in the inbox" hint="paste urls on the right to queue them" />;
  } else {
    body = (
      <>
        <MasonryGrid>
          {visible.map((i) => (
            <Card
              key={i.url}
              item={i}
              onInspect={setInspecting}
              onToggleSelect={handleToggleSelect}
              selected={sel.has(i.url)}
              state={cardState(i)}
              profileMatch={matchByUrl.get(i.url)}
            />
          ))}
        </MasonryGrid>
        <div ref={sentinelRef} className="sentinel" />
      </>
    );
  }

  return (
    <div id="inbox-page" className="hub-page hub-page-fill">
      <HubControls>
        <SourceFilter value={source} onChange={handleSourceChange} />
        <span className="count">
          <CountUp value={items.length} />
          {q.data && q.data.length !== items.length ? (
            <>
              {" "}
              of <CountUp value={q.data.length} />
            </>
          ) : (
            ""
          )}{" "}
          pending
        </span>
      </HubControls>
      <div className="hub-body hub-row">
        <div className="grid-col">{body}</div>
        <aside className="rail">
          <div className="rail-scroll">
            <RailWidget title="add to queue" prefKey={RAIL_QUEUE_PREF} defaultOpen>
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
                <SourcePullMenu onPull={handleSelectivePull} disabled={refreshSources.isPending} />
              </div>
            </RailWidget>

            <RailWidget title="profile match" prefKey={RAIL_MATCH_PREF}>
              <button
                className="btn"
                onClick={handleRankByProfile}
                disabled={profileRank.data?.state === "running" || startProfileRank.isPending}
              >
                {profileRank.data?.state === "running"
                  ? "ranking by profile..."
                  : allPicks.length
                    ? "re-rank by profile"
                    : "rank by profile"}
              </button>
              {allPicks.length > 0 ? (
                <label className="profile-rank-toggle">
                  <input
                    type="checkbox"
                    checked={showMatches}
                    onChange={(e) => setShowMatchesPref(e.target.checked)}
                  />
                  show matches in grid
                </label>
              ) : null}
              {showMatches && allPicks.length > 0 && profileRank.data?.state !== "running" ? (
                <div className="profile-rank-batch">
                  <button
                    className="btn"
                    onClick={() => setBatch((b) => (b + 1) % batchCount)}
                    disabled={batchCount <= 1}
                  >
                    reroll
                  </button>
                  <span className="batch-indicator" aria-live="polite">
                    batch {activeBatch + 1}/{batchCount}
                  </span>
                  <button
                    className="btn ghost"
                    onClick={() => setBatch(0)}
                    disabled={activeBatch === 0}
                  >
                    reset
                  </button>
                </div>
              ) : null}
              <div
                className={`profile-rank-status${profileRank.data?.state === "running" ? " running" : ""}`}
              >
                {profileRank.data?.state === "running" ? (
                  <span>scoring the full inbox · this can take a minute or two</span>
                ) : profileRank.data?.picks.length ? (
                  <span>
                    {activeHighlightCount} highlighted · {profileRank.data.candidates} text items
                    scored
                    {profileRank.data.generated_at
                      ? ` · updated ${profileRank.data.generated_at.slice(0, 10)}`
                      : ""}
                  </span>
                ) : (
                  <span>find the 30 pending items that best fit your interest profile</span>
                )}
                {profileRank.isError ? (
                  <span className="profile-rank-error">rank status unavailable</span>
                ) : null}
                {profileRank.data?.state === "error" ? (
                  <span className="profile-rank-error">{profileRank.data.detail}</span>
                ) : null}
              </div>
            </RailWidget>

            <RailWidget title="ingest selection" prefKey={RAIL_INGEST_PREF} defaultOpen>
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
            </RailWidget>

            {/* Always mounted: the rail is four widgets, always. An idle
                section stays out of the way by staying collapsed, not by
                disappearing — the gate below only decides whether there is
                anything to show inside it. */}
            <RailWidget
              title="job progress"
              prefKey={RAIL_JOB_PREF}
              forceOpenKey={job.data?.running ? job.data.total : null}
            >
              {job.data && (job.data.running || job.data.total > 0) ? (
                <div className={`progress${job.data.running ? " running" : ""}`}>
                  <span className="progress-line">
                    <IngestRing
                      done={job.data.done}
                      total={job.data.total}
                      running={job.data.running}
                    />
                    <span>
                      <ScrambleStatus text={job.data.running ? "running" : "done"} />
                      {" · "}
                      {job.data.done}/{job.data.total}
                      {job.data.running && elapsed ? ` · ${elapsed}` : ""}
                    </span>
                  </span>
                  {job.data.running ? (
                    <>
                      <span className="progress-current" title={currentTitle}>
                        <ScrambleStatus text={currentTitle} />
                      </span>
                      <span className="progress-hint">enrichment takes ~2 min per item</span>
                    </>
                  ) : null}
                  {job.data.failures.length > 0 ? (
                    <span className="progress-failed">{job.data.failures.length} failed</span>
                  ) : null}
                </div>
              ) : null}
            </RailWidget>
          </div>

          <div className="rail-footer">
            <span className="selcount">{sel.size} selected</span>
            <button
              className="btn primary"
              onClick={handleIngest}
              disabled={sel.size === 0 || ingest.isPending}
            >
              ingest
            </button>
          </div>
        </aside>
      </div>
      {inspecting ? (
        <QueueItemViewer
          item={inspecting}
          selected={sel.has(inspecting.url)}
          onToggleSelect={handleToggleSelect}
          onClose={() => setInspecting(null)}
        />
      ) : null}
    </div>
  );
}
