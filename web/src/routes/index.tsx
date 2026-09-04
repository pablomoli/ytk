import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { HubControls } from "../components/HubControls";
import { MasonryGrid } from "../components/MasonryGrid";
import { Skeletons } from "../components/Skeletons";
import { ErrorState } from "../components/StateViews";
import { Button } from "../components/ui/button";
import { useAnswerAsk, useOutbox } from "../api/outbox";
import type { LoopError, OutboxAsk, ProposedLink, WorkingOn } from "../api/outbox";
import "../styles.css";

export const Route = createFileRoute("/")({
  component: DigestPage,
});

// Quality kinds wear the accent; intent and the rest stay muted. The split
// mirrors the digest order itself (spec: quality first).
const QUALITY_KINDS = new Set(["transcript junk", "blind item", "duplicate", "grader bounce, twice"]);

type Variant = "grid" | "poster";

/* Stroke glyphs, lucide-shaped but inlined: lucide-react is not a dependency
   here and one icon set is not worth adding one. */
const GLYPHS: Record<string, string[]> = {
  "transcript junk": [
    "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z",
    "M14 2v6h6",
    "m9.5 12.5 5 5",
    "m14.5 12.5-5 5",
  ],
  "blind item": [
    "M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94",
    "M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19",
    "M14.12 14.12a3 3 0 1 1-4.24-4.24",
    "m1 1 22 22",
  ],
  duplicate: [
    "M20 9h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2z",
    "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
  ],
  "grader bounce, twice": ["M3 12a9 9 0 1 0 3-6.7L3 8", "M3 3v5h5"],
  "intent missing": [
    "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3",
    "M12 17h.01",
  ],
  connections: [
    "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71",
    "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
  ],
  check: ["M20 6 9 17l-5-5"],
  x: ["M18 6 6 18", "m6 6 12 12"],
  pencil: [
    "M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z",
  ],
  fallback: ["M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0", "M12 8v4l2.5 2.5"],
};

function Glyph({ name, className }: { name: string; className?: string }) {
  const paths = GLYPHS[name] ?? GLYPHS.fallback;
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

// Icons over labels: the kind reads from the glyph and its tint; the words
// live in the tooltip, with the source riding along.
function KindMark({ ask }: { ask: OutboxAsk }) {
  const label = ask.source ? `${ask.subkind} · ${ask.source}` : ask.subkind;
  return (
    <span
      role="img"
      aria-label={ask.subkind}
      title={label}
      className={`shrink-0 ${QUALITY_KINDS.has(ask.subkind) ? "text-accent" : "text-mute"}`}
    >
      <Glyph name={ask.subkind} />
    </span>
  );
}

function Chip({
  label,
  active,
  onToggle,
}: {
  label: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <Button
      size="sm"
      variant={active ? "secondary" : "outline"}
      aria-pressed={active}
      className="h-6 min-h-6 min-w-0 rounded-full px-2.5 py-0 text-xs"
      onClick={onToggle}
    >
      {label}
    </Button>
  );
}

function ConnectionsAnswer({
  links,
  struck,
  onToggle,
  pending,
  onSend,
  linksOpen,
}: {
  links: ProposedLink[];
  struck: Set<string>;
  onToggle: (target: string) => void;
  pending: boolean;
  onSend: (choice: string, note?: string) => void;
  linksOpen: boolean;
}) {
  const kept = links.filter((l) => !struck.has(l.target));
  // All kept -> approve; some -> strike some (survivors as JSON in the
  // answer text, what apply_links parses); zero kept behaves as none.
  const sendKept = () => {
    if (kept.length === links.length) onSend("approve");
    else if (kept.length === 0) onSend("none");
    else onSend("strike some", JSON.stringify(kept.map((l) => l.target)));
  };
  return (
    <div className="flex flex-col gap-2">
      {linksOpen ? (
        <div className="flex flex-col gap-1.5">
          {links.map((l) => (
            <label key={l.target} className="flex items-start gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={!struck.has(l.target)}
                onChange={() => onToggle(l.target)}
                className="mt-1 accent-current"
                aria-label={`link ${l.target}`}
              />
              <span className="text-ink2">
                <strong className="text-ink">[[{l.target}]]</strong> — {l.argument}
              </span>
            </label>
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-1.5">
        <Button size="sm" variant="secondary" disabled={pending} onClick={sendKept}>
          {kept.length === links.length
            ? "approve"
            : kept.length
              ? `approve ${kept.length} of ${links.length}`
              : "none survive"}
        </Button>
        <Button size="sm" variant="outline" disabled={pending} onClick={() => onSend("none")}>
          none
        </Button>
      </div>
    </div>
  );
}

/* Universal verbs render as icons; anything kind-specific keeps its words.
   The aria-label is the option string itself, so answers stay addressable
   by name in tests and by screen readers. */
const OPTION_GLYPH: Record<string, string> = { drop: "x", "accept as is": "check" };

function AskCard({
  ask,
  poster,
  onAnswered,
}: {
  ask: OutboxAsk;
  poster: boolean;
  onAnswered: (line: string) => void;
}) {
  const answer = useAnswerAsk();
  const [saying, setSaying] = useState(false);
  const [text, setText] = useState("");
  // Connections: struck targets are removed from the answer; the rest
  // survive. Controlled here, never read back from the DOM.
  const [struck, setStruck] = useState<Set<string>>(new Set());
  // Folded sections open per key; chips toggle them independently.
  const [open, setOpen] = useState<Set<string>>(new Set());
  const options = ask.proposal.options ?? [];
  const links = ask.proposal.links ?? [];
  const isConnections = ask.subkind === "connections" && links.length > 0;
  const isIntent = ask.subkind === "intent missing";
  const objections = ask.objections ?? [];

  const toggleOpen = (key: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const send = (choice: string, note?: string) => {
    answer.mutate(
      note ? { ask_id: ask.ask_id, choice, text: note } : { ask_id: ask.ask_id, choice },
      { onSuccess: () => onAnswered(`${ask.title ?? ask.url ?? "item"} — ${choice}`) },
    );
  };

  const title = ask.url ? (
    <a href={ask.url} target="_blank" rel="noreferrer" className="text-inherit no-underline hover:text-accent">
      {ask.title ?? ask.url}
    </a>
  ) : (
    (ask.title ?? "untitled")
  );

  const hasChips = Boolean(ask.draft) || objections.length > 0 || isConnections;
  const chips = (
    <>
      {ask.draft ? (
        <Chip label="draft" active={open.has("draft")} onToggle={() => toggleOpen("draft")} />
      ) : null}
      {objections.map((o, i) => (
        <Chip
          key={`obj-${i}`}
          label={o.check ?? "objection"}
          active={open.has(`obj-${i}`)}
          onToggle={() => toggleOpen(`obj-${i}`)}
        />
      ))}
      {isConnections ? (
        <Chip
          label={`${links.length} links`}
          active={open.has("links")}
          onToggle={() => toggleOpen("links")}
        />
      ) : null}
    </>
  );

  const openSections = (
    <>
      {ask.draft && open.has("draft") ? (
        <div className="flex flex-col gap-1.5 rounded-card border border-line bg-bg3 p-3 text-sm">
          {ask.draft.thesis ? <p className="m-0 font-medium text-ink">{ask.draft.thesis}</p> : null}
          {ask.draft.summary ? <p className="m-0 text-ink2">{ask.draft.summary}</p> : null}
          {ask.draft.key_concepts?.length ? (
            <ul className="m-0 list-disc pl-5 text-ink2">
              {ask.draft.key_concepts.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : null}
          {ask.draft.take_response ? (
            <p className="m-0 italic text-ink2">{ask.draft.take_response}</p>
          ) : null}
        </div>
      ) : null}
      {objections.map((o, i) =>
        open.has(`obj-${i}`) ? (
          <p key={`obj-open-${i}`} className="m-0 text-sm text-ink2">
            {o.check ? <strong className="text-ink">{o.check}: </strong> : null}
            {o.detail}
          </p>
        ) : null,
      )}
    </>
  );

  const sayBox = (
    <textarea
      className="w-full rounded-card border border-line bg-bg3 p-2.5 text-ink text-sm"
      rows={2}
      value={text}
      placeholder="type here, then pick an option — your words ride the choice"
      onChange={(e) => setText(e.target.value)}
    />
  );

  const pills = isConnections ? (
    <ConnectionsAnswer
      links={links}
      struck={struck}
      onToggle={(target) =>
        setStruck((prev) => {
          const next = new Set(prev);
          if (next.has(target)) next.delete(target);
          else next.add(target);
          return next;
        })
      }
      pending={answer.isPending}
      onSend={send}
      linksOpen={open.has("links")}
    />
  ) : (
    <div className="flex flex-wrap items-center gap-1.5">
      {options.map((option) => {
        // Intent asks only accept a bare "just want it"/"drop": the point of
        // the ask is the words, so intent/reaction stay dark until typed.
        const needsText = isIntent && (option === "intent" || option === "reaction");
        const glyph = OPTION_GLYPH[option];
        return (
          <Button
            key={option}
            size={glyph ? "icon" : "sm"}
            variant={option === "drop" ? "outline" : "secondary"}
            disabled={answer.isPending || (needsText && !text.trim())}
            aria-label={option}
            title={option}
            className={glyph ? "size-9 min-h-9 min-w-9 rounded-full" : undefined}
            onClick={() => send(option, text.trim() || undefined)}
          >
            {glyph ? <Glyph name={glyph} /> : option}
          </Button>
        );
      })}
      {!isIntent ? (
        <Button
          size="icon"
          variant="ghost"
          aria-label="say more"
          title="say more"
          aria-pressed={saying}
          className="size-9 min-h-9 min-w-9 rounded-full"
          onClick={() => setSaying((s) => !s)}
        >
          <Glyph name="pencil" />
        </Button>
      ) : null}
    </div>
  );

  const error = answer.isError ? (
    <p className="m-0 sub text-accent" role="alert">
      answer failed: {String(answer.error)}
    </p>
  ) : null;

  if (poster && ask.thumbnail) {
    return (
      <article data-ask={ask.ask_id} data-kind={ask.subkind} className="card flex flex-col">
        <div className="relative">
          <img src={ask.thumbnail} alt="" className="w-full !h-auto block" />
          <div
            className="absolute inset-x-0 bottom-0 flex items-center gap-2 p-2 pt-6"
            style={{ background: "linear-gradient(transparent, rgba(0,0,0,0.78))" }}
          >
            <KindMark ask={ask} />
            <h3 className="title m-0 min-w-0 flex-1 truncate text-sm leading-snug text-white">
              {title}
            </h3>
          </div>
        </div>
        <div className="flex flex-col gap-1.5 p-2">
          {ask.proposal.why ? (
            <p className="m-0 text-xs italic text-ink2">{ask.proposal.why}</p>
          ) : null}
          {hasChips ? <div className="flex flex-wrap items-center gap-1">{chips}</div> : null}
          {openSections}
          {isIntent || saying ? sayBox : null}
          {pills}
          {error}
        </div>
      </article>
    );
  }

  return (
    <article data-ask={ask.ask_id} data-kind={ask.subkind} className="card flex flex-col">
      {ask.thumbnail ? <img src={ask.thumbnail} alt="" className="w-full !h-auto block" /> : null}
      <div className="flex flex-col gap-2 p-3">
        <div className="flex items-center gap-2">
          <KindMark ask={ask} />
          <h3 className="title m-0 min-w-0 flex-1 truncate text-base leading-snug text-ink">
            {title}
          </h3>
        </div>
        {ask.proposal.why ? (
          <p className="m-0 text-sm italic text-ink2">{ask.proposal.why}</p>
        ) : null}
        {hasChips ? <div className="flex flex-wrap items-center gap-1">{chips}</div> : null}
        {openSections}
        {isIntent || saying ? sayBox : null}
        {pills}
        {error}
      </div>
    </article>
  );
}

// The verb pipeline as the owner sees it. connect is a tail stage: it only
// runs after land, so it renders once reached, not as a pending promise.
const STAGE_TRAIL = ["read", "enrich", "checks", "grade", "land"] as const;
const STAGE_LABEL: Record<string, string> = {
  read: "read",
  enrich: "enrich",
  checks: "checks",
  grade: "grade",
  land: "land",
  connect: "connect",
  answer: "answer",
};

function useElapsed(startedAt: string | undefined): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!startedAt) return 0;
  const started = Date.parse(startedAt);
  return Number.isNaN(started) ? 0 : Math.max(0, Math.floor((now - started) / 1000));
}

function fmtElapsed(s: number): string {
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

function WorkingCard({ working, error }: { working: WorkingOn; error?: LoopError | null | undefined }) {
  const elapsed = useElapsed(working.started_at);
  const stageKey = working.stage?.key ?? working.action;
  const trailIdx = STAGE_TRAIL.indexOf(stageKey as (typeof STAGE_TRAIL)[number]);
  return (
    <article data-working-card className="card flex flex-col border-live">
      {working.thumbnail ? (
        <img src={working.thumbnail} alt="" className="w-full !h-auto block" />
      ) : null}
      <span
        className="absolute right-1.5 top-1.5 z-[2] rounded-full px-2 py-0.5 text-xs text-white"
        style={{ background: "rgba(0,0,0,0.55)" }}
      >
        {fmtElapsed(elapsed)}
      </span>
      <div className="flex flex-col gap-1.5 p-3">
        <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-1" aria-label="stage trail">
          {STAGE_TRAIL.map((stage, i) => {
            const state = trailIdx < 0 ? "pending" : i < trailIdx ? "done" : i === trailIdx ? "current" : "pending";
            return (
              <span key={stage} className="flex items-baseline gap-1.5">
                {i > 0 ? <span className="sub !text-mute">→</span> : null}
                <span
                  data-stage={stage}
                  data-state={state}
                  className={
                    state === "current"
                      ? "sub !text-live"
                      : state === "done"
                        ? "sub !text-ink2"
                        : "sub !text-mute"
                  }
                >
                  {stage}
                </span>
              </span>
            );
          })}
          {stageKey === "connect" ? (
            <span className="flex items-baseline gap-1.5">
              <span className="sub !text-mute">→</span>
              <span className="sub !text-live">connect</span>
            </span>
          ) : null}
        </div>
        <span className="sub !text-live">the loop is working</span>
        <span className="title text-base leading-snug truncate">{working.title}</span>
        <span className="sub !text-ink2">
          {STAGE_LABEL[stageKey] ?? stageKey}
          {working.stage?.detail ? ` — ${working.stage.detail}` : ""}
        </span>
        {error ? (
          <p className="m-0 sub !text-accent" role="status">
            hiccup {error.at.slice(11, 16)}Z — {error.reason} — the loop retries
          </p>
        ) : null}
      </div>
    </article>
  );
}

// Poll cadence while the loop is mid-verb (#199), and how long after an
// answer the strip keeps looking so it catches the verb starting.
const POLL_MS = 2500;
const ANSWER_POLL_WINDOW_MS = 90_000;

function initialVariant(): Variant {
  try {
    return new URLSearchParams(window.location.search).get("variant") === "poster"
      ? "poster"
      : "grid";
  } catch {
    return "grid";
  }
}

function DigestPage() {
  const outbox = useOutbox();
  const [receipts, setReceipts] = useState<string[]>([]);
  const [pollUntil, setPollUntil] = useState(0);
  const [variant, setVariant] = useState<Variant>(initialVariant);

  const pickVariant = (v: Variant) => {
    setVariant(v);
    try {
      const u = new URL(window.location.href);
      u.searchParams.set("variant", v);
      window.history.replaceState(null, "", u);
    } catch {
      /* history is a convenience, not a dependency */
    }
  };

  const working = outbox.data?.loop?.working ?? false;
  const { refetch } = outbox;
  useEffect(() => {
    const active = () => working || Date.now() < pollUntil;
    if (!active()) return;
    const t = setInterval(() => {
      if (active()) void refetch();
      else clearInterval(t);
    }, POLL_MS);
    return () => clearInterval(t);
  }, [working, pollUntil, refetch]);

  let body;
  if (outbox.isLoading) {
    body = <Skeletons count={3} />;
  } else if (outbox.isError) {
    body = <ErrorState error={outbox.error} onRetry={() => void outbox.refetch()} />;
  } else if (outbox.data) {
    const { asks, parked, loop } = outbox.data;
    const workingOn = loop?.working ? loop.working_on : null;
    const hasBoard = Boolean(workingOn) || asks.length > 0;
    body = (
      <>
        {hasBoard ? (
          <div className="flex items-center justify-end gap-1">
            <Button
              size="sm"
              variant={variant === "grid" ? "secondary" : "ghost"}
              aria-pressed={variant === "grid"}
              className="h-6 min-h-6 min-w-0 px-2 py-0 text-xs"
              onClick={() => pickVariant("grid")}
            >
              grid
            </Button>
            <Button
              size="sm"
              variant={variant === "poster" ? "secondary" : "ghost"}
              aria-pressed={variant === "poster"}
              className="h-6 min-h-6 min-w-0 px-2 py-0 text-xs"
              onClick={() => pickVariant("poster")}
            >
              poster
            </Button>
          </div>
        ) : null}
        {hasBoard ? (
          <MasonryGrid>
            {workingOn ? (
              <WorkingCard key="working" working={workingOn} error={loop?.last_error} />
            ) : null}
            {asks.map((ask) => (
              <AskCard
                key={ask.ask_id}
                ask={ask}
                poster={variant === "poster"}
                onAnswered={(line) => {
                  setReceipts((r) => [line, ...r]);
                  setPollUntil(Date.now() + ANSWER_POLL_WINDOW_MS);
                }}
              />
            ))}
          </MasonryGrid>
        ) : (
          <p className="text-ink2 italic">
            nothing needs you — <Link to="/library" className="text-accent">the library</Link> has
            everything kept, <Link to="/inbox" className="text-accent">the inbox</Link> takes more.
          </p>
        )}
        {receipts.length ? (
          <ul className="m-0 mt-4 flex list-none flex-col gap-1 p-0">
            {receipts.map((line, i) => (
              <li key={i} className="sub !text-live">
                answered: {line}
              </li>
            ))}
          </ul>
        ) : null}
        <footer className="mt-6 flex flex-col gap-1 border-t border-line pt-3">
          <span className="sub text-mute">
            {parked.count} parked
            {parked.oldest ? `, oldest from ${parked.oldest.slice(0, 10)}` : ""}
          </span>
          <span
            data-loop-strip
            className={loop && !loop.ok ? "sub text-accent" : "sub text-mute"}
          >
            {loop ? loop.line : "loop not running"}
          </span>
        </footer>
      </>
    );
  }

  return (
    <div id="digest-page" className="hub-page">
      <HubControls>
        <span className="count">
          {outbox.data ? `${outbox.data.asks.length} waiting` : "the digest"}
        </span>
      </HubControls>
      <div className="hub-body w-full">{body}</div>
    </div>
  );
}
