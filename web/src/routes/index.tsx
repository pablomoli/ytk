import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { HubControls } from "../components/HubControls";
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

function ConnectionsAnswer({
  links,
  struck,
  onToggle,
  pending,
  onSend,
}: {
  links: ProposedLink[];
  struck: Set<string>;
  onToggle: (target: string) => void;
  pending: boolean;
  onSend: (choice: string, note?: string) => void;
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
      <div className="flex flex-wrap items-center gap-2 pt-1">
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

function AskCard({ ask, onAnswered }: { ask: OutboxAsk; onAnswered: (line: string) => void }) {
  const answer = useAnswerAsk();
  const [saying, setSaying] = useState(false);
  const [text, setText] = useState("");
  // Connections: struck targets are removed from the answer; the rest
  // survive. Controlled here, never read back from the DOM.
  const [struck, setStruck] = useState<Set<string>>(new Set());
  const options = ask.proposal.options ?? [];
  const links = ask.proposal.links ?? [];
  const isConnections = ask.subkind === "connections" && links.length > 0;

  const send = (choice: string, note?: string) => {
    answer.mutate(
      note ? { ask_id: ask.ask_id, choice, text: note } : { ask_id: ask.ask_id, choice },
      { onSuccess: () => onAnswered(`${ask.title ?? ask.url ?? "item"} — ${choice}`) },
    );
  };

  return (
    <article data-ask={ask.ask_id} className="card p-4 flex flex-col gap-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <span
          className={`sub ${QUALITY_KINDS.has(ask.subkind) ? "!text-accent" : "!text-ink2"}`}
        >
          {ask.subkind}
        </span>
        {ask.source ? <span className="sub !text-mute">{ask.source}</span> : null}
      </div>
      <h3 className="title text-lg leading-snug">
        {ask.url ? (
          <a href={ask.url} target="_blank" rel="noreferrer" className="text-ink no-underline hover:text-accent">
            {ask.title ?? ask.url}
          </a>
        ) : (
          (ask.title ?? "untitled")
        )}
      </h3>
      {ask.thumbnail ? (
        <img
          src={ask.thumbnail}
          alt=""
          className="max-h-40 w-fit rounded-card border border-line object-cover"
        />
      ) : null}
      {ask.draft ? (
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
      {ask.objections?.length ? (
        <div className="flex flex-col gap-1">
          <span className="sub !text-accent">the grader said</span>
          <ul className="m-0 list-disc pl-5 text-sm text-ink2">
            {ask.objections.map((o, i) => (
              <li key={i}>
                {o.check ? <strong className="text-ink">{o.check}: </strong> : null}
                {o.detail}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {!ask.objections?.length && ask.proposal.why ? (
        <p className="m-0 italic text-ink2 text-sm">{ask.proposal.why}</p>
      ) : null}
      {isConnections ? (
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
        />
      ) : null}
      {!isConnections ? (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {options.map((option) => (
            <Button
              key={option}
              size="sm"
              variant={option === "drop" ? "outline" : "secondary"}
              disabled={answer.isPending}
              onClick={() => send(option, text.trim() || undefined)}
            >
              {option}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={() => setSaying((s) => !s)}>
            say more
          </Button>
        </div>
      ) : null}
      {saying ? (
        <textarea
          className="w-full rounded-card border border-line bg-bg3 p-2.5 text-ink text-sm"
          rows={2}
          value={text}
          placeholder="type here, then pick an option — your words ride the choice"
          onChange={(e) => setText(e.target.value)}
        />
      ) : null}
      {answer.isError ? (
        <p className="m-0 sub text-accent" role="alert">
          answer failed: {String(answer.error)}
        </p>
      ) : null}
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
    <article data-working-card className="card p-4 flex flex-col gap-2.5 border-live">
      <div className="flex items-baseline justify-between gap-3">
        <span className="sub !text-live">the loop is working</span>
        <span className="sub !text-mute">{fmtElapsed(elapsed)}</span>
      </div>
      <div className="flex items-center gap-3">
        {working.thumbnail ? (
          <img
            src={working.thumbnail}
            alt=""
            className="max-h-20 w-fit shrink-0 rounded-card border border-line"
          />
        ) : null}
        <div className="flex flex-col gap-1 min-w-0">
          <span className="title text-base leading-snug truncate">{working.title}</span>
          <span className="sub !text-ink2">
            {STAGE_LABEL[stageKey] ?? stageKey}
            {working.stage?.detail ? ` — ${working.stage.detail}` : ""}
          </span>
        </div>
      </div>
      <div className="flex items-baseline gap-1.5" aria-label="stage trail">
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
      {error ? (
        <p className="m-0 sub !text-accent" role="status">
          hiccup {error.at.slice(11, 16)}Z — {error.reason} — the loop retries
        </p>
      ) : null}
    </article>
  );
}

// Poll cadence while the loop is mid-verb (#199), and how long after an
// answer the strip keeps looking so it catches the verb starting.
const POLL_MS = 2500;
const ANSWER_POLL_WINDOW_MS = 90_000;

function DigestPage() {
  const outbox = useOutbox();
  const [receipts, setReceipts] = useState<string[]>([]);
  const [pollUntil, setPollUntil] = useState(0);

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
    body = (
      <>
        {workingOn ? <WorkingCard working={workingOn} error={loop?.last_error} /> : null}
        {asks.length ? (
          <div className="flex flex-col gap-3">
            {asks.map((ask) => (
              <AskCard
                key={ask.ask_id}
                ask={ask}
                onAnswered={(line) => {
                  setReceipts((r) => [line, ...r]);
                  setPollUntil(Date.now() + ANSWER_POLL_WINDOW_MS);
                }}
              />
            ))}
          </div>
        ) : workingOn ? null : (
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
      <div className="hub-body mx-auto w-full max-w-2xl">{body}</div>
    </div>
  );
}
