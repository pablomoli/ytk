import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { HubControls } from "../components/HubControls";
import { Skeletons } from "../components/Skeletons";
import { ErrorState } from "../components/StateViews";
import { Button } from "../components/ui/button";
import { useAnswerAsk, useOutbox } from "../api/outbox";
import type { OutboxAsk } from "../api/outbox";
import "../styles.css";

export const Route = createFileRoute("/")({
  component: DigestPage,
});

// Quality kinds wear the accent; intent and the rest stay muted. The split
// mirrors the digest order itself (spec: quality first).
const QUALITY_KINDS = new Set(["transcript junk", "blind item", "duplicate", "grader bounce, twice"]);

function AskCard({ ask, onAnswered }: { ask: OutboxAsk; onAnswered: (line: string) => void }) {
  const answer = useAnswerAsk();
  const [saying, setSaying] = useState(false);
  const [text, setText] = useState("");
  const options = ask.proposal.options ?? [];

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
      {ask.proposal.why ? <p className="m-0 italic text-ink2 text-sm">{ask.proposal.why}</p> : null}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {options.map((option) => (
          <Button
            key={option}
            size="sm"
            variant={option === "drop" ? "outline" : "secondary"}
            disabled={answer.isPending}
            onClick={() => send(option)}
          >
            {option}
          </Button>
        ))}
        <Button size="sm" variant="ghost" onClick={() => setSaying((s) => !s)}>
          say more
        </Button>
      </div>
      {saying ? (
        <div className="flex flex-col gap-2">
          <textarea
            className="w-full rounded-card border border-line bg-bg3 p-2.5 text-ink text-sm"
            rows={2}
            value={text}
            placeholder="your words land as the answer text"
            onChange={(e) => setText(e.target.value)}
          />
          <div>
            <Button
              size="sm"
              disabled={answer.isPending || !text.trim()}
              onClick={() => send(options[0] ?? "edit", text.trim())}
            >
              answer
            </Button>
          </div>
        </div>
      ) : null}
      {answer.isError ? (
        <p className="m-0 sub text-accent" role="alert">
          answer failed: {String(answer.error)}
        </p>
      ) : null}
    </article>
  );
}

function DigestPage() {
  const outbox = useOutbox();
  const [receipts, setReceipts] = useState<string[]>([]);

  let body;
  if (outbox.isLoading) {
    body = <Skeletons count={3} />;
  } else if (outbox.isError) {
    body = <ErrorState error={outbox.error} onRetry={() => void outbox.refetch()} />;
  } else if (outbox.data) {
    const { asks, parked } = outbox.data;
    body = (
      <>
        {asks.length ? (
          <div className="flex flex-col gap-3">
            {asks.map((ask) => (
              <AskCard
                key={ask.ask_id}
                ask={ask}
                onAnswered={(line) => setReceipts((r) => [line, ...r])}
              />
            ))}
          </div>
        ) : (
          <p className="text-ink2 italic">
            nothing needs you — <Link to="/library">the library</Link> has everything kept,{" "}
            <Link to="/inbox">the inbox</Link> takes more.
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
          <span className="sub text-mute">loop not running — arrives with P5</span>
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
