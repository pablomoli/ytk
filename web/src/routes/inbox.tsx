import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import {
  ArrowClockwise,
  ArrowCounterClockwise,
  ArrowsClockwise,
  X,
} from "@phosphor-icons/react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useQueue } from "../api/queue";
import type { QueueItem } from "../api/queue";
import { useAddUrls, useRefreshSources, useIngest } from "../api/mutations";
import { useJobStatus } from "../api/job";
import { useProfileRank, useStartProfileRank } from "../api/profileRank";
import { apiGet } from "../api/client";
import { QueueItemViewer } from "../components/QueueItemViewer";
import { SourceSelect } from "../components/SourceSelect";
import { SourcePullMenu } from "../components/SourcePullMenu";
import { Card } from "../components/Card";
import { MasonryGrid } from "../components/MasonryGrid";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { CountUp } from "../components/CountUp";
import { InboxJobProgress } from "../components/InboxJobProgress";
import { ScrambleStatus } from "../components/ScrambleStatus";
import { RailWidget } from "../components/RailWidget";
import { Button } from "../components/ui/button";
import { IconButton } from "../components/ui/icon-button";
import { useInfiniteWindow } from "../lib/useInfiniteWindow";
import { useBatchCursor } from "../lib/useBatchCursor";
import { filterAndSortQueue } from "../lib/queueItems";
import { formatElapsed } from "../lib/elapsed";
import { pullSummary, pullingLabel } from "../lib/pullStatus";
import {
  INBOX_SOURCES_PREF,
  PROFILE_MATCHES_PREF,
  RAIL_QUEUE_PREF,
  RAIL_MATCH_PREF,
  RAIL_INGEST_PREF,
  RAIL_SOURCES_PREF,
  getPref,
  getStringPref,
  setPref,
  setStringPref,
} from "../lib/prefs";
import type { SourceSelection } from "../lib/sourceFilter";
import { parseSources, serializeSources } from "../lib/sourceFilter";
import "../styles.css";

export const Route = createFileRoute("/inbox")({
  validateSearch: (s: Record<string, unknown>): { sources?: string | undefined } => ({
    sources: typeof s.sources === "string" ? s.sources : undefined,
  }),
  component: InboxPage,
});

const fetchTags = () => apiGet<{ tags: string[] }>("/api/tags").then((r) => r.tags);

// Must match the backend's page_size (rank_all_pending), so one UI batch equals
// one stratified block of the ranked pool.
const PROFILE_BATCH_SIZE = 30;

function InboxPage() {
  const { sources } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });

  /* The URL is the authority for what is on screen, so back/forward restore the
     filter exactly. The stored preference only supplies a starting point when
     arriving at /inbox with no parameter at all — otherwise a remembered filter
     would silently override a link someone deliberately followed (#126). */
  const selection = useMemo(
    () => parseSources(sources ?? getStringPref(INBOX_SOURCES_PREF)),
    [sources],
  );
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
  const [reflection, setReflection] = useState("");
  /* First flagged, unanswered item in the selection, in queue order. One
     question is enough prompting; the rest keep their card badges (#98). */
  const reflectTarget = useMemo(
    () =>
      (q.data ?? []).find((i) => sel.has(i.url) && i.reflection_question && !i.reflection_answered),
    [q.data, sel],
  );
  /* A typed answer must never ride along under a different item's url. */
  useEffect(() => {
    setReflection("");
  }, [reflectTarget?.url]);
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
  // The cursor persists keyed to the snapshot id, so a refresh keeps the
  // user's place while a fresh ranking starts at batch 1 (#138).
  const cursor = useBatchCursor(profileRank.data?.generated_at, batchCount);
  const activeBatch = cursor.batch;
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
    const filtered = filterAndSortQueue(q.data ?? [], selection);
    if (matchByUrl.size === 0) return filtered;
    // Matched picks lead the inbox; both groups keep filtered's newest-first
    // order, so the freshest item leads within the highlighted set. Unscored
    // items are never hidden — they just follow the matches.
    const matched = filtered.filter((i) => matchByUrl.has(i.url));
    const rest = filtered.filter((i) => !matchByUrl.has(i.url));
    return [...matched, ...rest];
  }, [q.data, selection, matchByUrl]);
  const activeHighlightCount = useMemo(
    () => items.filter((item) => matchByUrl.has(item.url)).length,
    [items, matchByUrl],
  );
  // Progressively renders more of `items` as the sentinel scrolls into view;
  // not a bounded/sliding window, the visible count only grows.
  const { visible, sentinelRef } = useInfiniteWindow(items, 60, sources ?? "");

  // The in-flight item, named. A batch runs ~2 minutes per video, so a bare
  // "0/3" sits unchanged long enough to read as broken; showing which video is
  // being worked, and for how long, is the difference between stalled and slow.
  const currentTitle = useMemo(() => {
    const url = job.data?.current;
    if (!url) return "";
    const item = (q.data ?? []).find((i) => i.url === url);
    return item?.text || item?.author || url;
  }, [q.data, job.data]);

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

  /* Writes the choice to the URL and mirrors it into the preference, so a later
     visit with no parameter starts where this one left off. Both hold the same
     serialization, so the two cannot drift into different encodings. */
  const handleSourceChange = (next: SourceSelection) => {
    const encoded = serializeSources(next);
    setStringPref(INBOX_SOURCES_PREF, encoded ?? null);
    void navigate({ search: { sources: encoded } });
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

  /* Remembered separately from the mutation so the in-flight line can name what
     is being fetched. react-query exposes the result but not the variables in a
     form that survives the pending render here, and "loading..." for up to a
     minute of network work says nothing about whether it is doing what you
     asked. */
  const [pulling, setPulling] = useState<string[] | undefined>(undefined);

  const handleRefresh = () => {
    setPulling(undefined); // plain refresh: all sources, cadence-respecting
    refreshSources.mutate(undefined);
  };

  const handleSelectivePull = (only: string[]) => {
    setPulling(only);
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
    const answer = reflection.trim();
    ingest.mutate(
      {
        urls: [...sel],
        tags: [...chosenTags],
        thought,
        // Spread so an empty answer sends no reflections key at all.
        ...(reflectTarget && answer ? { reflections: { [reflectTarget.url]: answer } } : {}),
      },
      {
        onSuccess: () => {
          setSel(new Set());
          setChosenTags(new Set());
          setThought("");
          setReflection("");
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
      <div className="flex min-h-0 flex-1 flex-col items-stretch gap-4 p-4 min-[761px]:flex-row">
        <div className="order-2 flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-x-hidden overflow-y-auto px-1.5 pt-1.5 [mask-image:linear-gradient(to_bottom,transparent_0,#000_14px,#000_100%)] min-[761px]:order-none">
          {body}
        </div>
        <aside
          className="rail order-1 flex max-h-[52dvh] w-full flex-none flex-col gap-3.5 overflow-hidden rounded-[10px] border border-line bg-bg1 p-4 min-[761px]:order-none min-[761px]:max-h-none min-[761px]:w-80 min-[761px]:basis-80"
          aria-label="Inbox controls"
        >
          <InboxJobProgress job={job.data} currentTitle={currentTitle} elapsed={elapsed} />
          <div className="rail-scroll flex min-h-0 flex-1 flex-col gap-3.5 overflow-y-auto pb-2">
            <RailWidget
              title="sources"
              prefKey={RAIL_SOURCES_PREF}
              defaultOpen
              meta={
                <>
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
                </>
              }
            >
              <SourceSelect selection={selection} onChange={handleSourceChange} />
            </RailWidget>

            <RailWidget title="add to queue" prefKey={RAIL_QUEUE_PREF} defaultOpen>
              <label className="font-data text-xs tracking-[0.04em] text-ink2" htmlFor="inbox-urls">
                URLs
              </label>
              <textarea
                id="inbox-urls"
                className="min-h-11"
                value={urlsText}
                onChange={handleUrlsChange}
                placeholder="Example: https://youtube.com/watch?v=..."
                rows={2}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={handleAdd} disabled={addUrls.isPending}>
                  Add
                </Button>
                <IconButton
                  label="Refresh sources"
                  onClick={handleRefresh}
                  disabled={refreshSources.isPending}
                  variant="secondary"
                >
                  <ArrowClockwise />
                </IconButton>
                <SourcePullMenu onPull={handleSelectivePull} disabled={refreshSources.isPending} />
              </div>
              {/* Disabled buttons were the only sign a pull was running, which
                  reads as a dead UI rather than a busy one. This says what is
                  being fetched, then what it found. */}
              {refreshSources.isPending ? (
                <div className="pull-status busy" role="status">
                  <span className="dot-spinner" aria-hidden="true" />
                  <span>{pullingLabel(pulling)}</span>
                </div>
              ) : refreshSources.isError ? (
                <div className="pull-status failed" role="status">
                  pull failed — {(refreshSources.error as Error).message}
                </div>
              ) : refreshSources.data ? (
                <div className="pull-status" role="status">
                  <ScrambleStatus text={pullSummary(refreshSources.data)} />
                </div>
              ) : null}
            </RailWidget>

            <RailWidget title="profile match" prefKey={RAIL_MATCH_PREF}>
              <Button
                variant="secondary"
                onClick={handleRankByProfile}
                disabled={profileRank.data?.state === "running" || startProfileRank.isPending}
              >
                {profileRank.data?.state === "running"
                  ? "ranking by profile..."
                  : allPicks.length
                    ? "re-rank by profile"
                    : "rank by profile"}
              </Button>
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
                <div className="mt-2 flex items-center gap-2">
                  <IconButton
                    label="reroll"
                    onClick={cursor.advance}
                    disabled={batchCount <= 1}
                    variant="secondary"
                  >
                    <ArrowsClockwise />
                  </IconButton>
                  <span className="batch-indicator" aria-live="polite">
                    batch {activeBatch + 1}/{batchCount}
                  </span>
                  <IconButton
                    label="reset"
                    onClick={cursor.reset}
                    disabled={activeBatch === 0}
                    variant="ghost"
                  >
                    <ArrowCounterClockwise />
                  </IconButton>
                </div>
              ) : null}
              <div
                className={`profile-rank-status${profileRank.data?.state === "running" ? " running" : ""}`}
              >
                {profileRank.data?.state === "running" ? (
                  <span>scoring the inbox</span>
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

            {sel.size > 0 ? (
              <RailWidget title="ingest selection" prefKey={RAIL_INGEST_PREF} defaultOpen>
                <fieldset className="m-0 border-0 p-0">
                  <legend className="mb-1.5 font-data text-xs tracking-[0.04em] text-ink2">
                    Tags
                  </legend>
                  <div className="flex flex-wrap gap-2">
                    {(tags.data ?? []).map((t) => (
                      <Button
                        key={t}
                        size="sm"
                        variant={chosenTags.has(t) ? "default" : "outline"}
                        aria-pressed={chosenTags.has(t)}
                        onClick={() => handleToggleTag(t)}
                      >
                        {t}
                      </Button>
                    ))}
                  </div>
                </fieldset>
                {reflectTarget ? (
                  <div className="mb-2 font-data text-[12.5px]" data-testid="rail-reflection">
                    <div className="text-mute">
                      {(reflectTarget.text || reflectTarget.author || reflectTarget.url).slice(
                        0,
                        120,
                      )}
                      {reflectTarget.text && reflectTarget.author
                        ? ` · ${reflectTarget.author}`
                        : ""}
                    </div>
                    <p className="my-1 italic text-ink2">{reflectTarget.reflection_question}</p>
                    <label
                      className="mb-1 block text-xs tracking-[0.04em] text-ink2"
                      htmlFor="inbox-reflection"
                    >
                      Reflection
                    </label>
                    <input
                      id="inbox-reflection"
                      className="min-h-11 w-full rounded-[6px] border border-line bg-bg3 px-2 py-1.5 text-ink placeholder:text-mute"
                      placeholder="Example: it connects to my current work"
                      value={reflection}
                      onChange={(e) => setReflection(e.target.value)}
                    />
                  </div>
                ) : null}
                <label
                  className="mb-1 block font-data text-xs tracking-[0.04em] text-ink2"
                  htmlFor="inbox-thought"
                >
                  Thought
                </label>
                <textarea
                  id="inbox-thought"
                  className="min-h-24"
                  value={thought}
                  onChange={handleThoughtChange}
                  placeholder="Example: compare this with the last saved source"
                />
              </RailWidget>
            ) : null}
          </div>

          {sel.size > 0 ? (
            <div className="rail-footer flex flex-none items-center gap-2 border-t border-line pt-3">
              <IconButton label="Clear selection" onClick={() => setSel(new Set())}>
                <X />
              </IconButton>
              <Button className="flex-1" onClick={handleIngest} disabled={ingest.isPending}>
                Ingest {sel.size} {sel.size === 1 ? "item" : "items"}
              </Button>
            </div>
          ) : null}
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
