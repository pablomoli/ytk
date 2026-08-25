import { useEffect, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useLsdDeck, useLsdRuns, useRateCard } from "../api/lsd";
import { HubControls } from "../components/HubControls";
import { Skeletons } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/StateViews";
import { Button } from "../components/ui/button";
import { SegmentedControl, SegmentedControlItem } from "../components/ui/segmented-control";
import "../styles.css";

export const Route = createFileRoute("/lsd")({
  component: LsdPage,
});

const SCORES = ["1", "2", "3", "4", "5"] as const;
const YES = 4;

// One question for every kind: the deck exists to show new things, not to
// ship them. 4+ means it was new and it holds.
const QUESTION = "did this show you something you had not seen?";

function Scaffold({ label, text }: { label: string; text: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-data text-xs tracking-[0.08em] text-mute uppercase">{label}</span>
      <p className="m-0 text-sm leading-relaxed text-ink2">{text}</p>
    </div>
  );
}

/* Section 53's rating deck. One card at a time, pool never shown, parents
   hidden until the card is rated: a NEAR pair's twin titles would unblind
   the rater. Order is the deck's own shuffle; rated cards are skipped. */
function LsdPage() {
  const runs = useLsdRuns();
  const [runId, setRunId] = useState<string | null>(null);
  const activeRun = runId ?? runs.data?.[0]?.run_id ?? null;
  const deck = useLsdDeck(activeRun);
  const rate = useRateCard();

  const [revealed, setRevealed] = useState<string | null>(null);
  const [score, setScore] = useState<string>("");
  const [note, setNote] = useState("");

  const cards = useMemo(() => deck.data?.cards ?? [], [deck.data]);
  const ratings = useMemo(() => deck.data?.ratings ?? {}, [deck.data]);
  const pending = useMemo(() => cards.filter((c) => !(c.id in ratings)), [cards, ratings]);
  const current = revealed ? (cards.find((c) => c.id === revealed) ?? null) : (pending[0] ?? null);
  const done = cards.length - pending.length;

  const submit = (value: string) => {
    if (!current || !activeRun) return;
    setScore(value);
    rate.mutate(
      { run_id: activeRun, candidate_id: current.id, score: Number(value), note },
      { onSuccess: () => setRevealed(current.id) },
    );
  };

  const next = () => {
    setRevealed(null);
    setScore("");
    setNote("");
  };

  // Digits rate, Enter advances: a 60-card deck should not need the mouse.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      if (!revealed && SCORES.includes(e.key as (typeof SCORES)[number])) submit(e.key);
      if (revealed && e.key === "Enter") next();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (runs.isLoading || deck.isLoading) return <Skeletons count={1} />;
  if (runs.isError) return <ErrorState error={runs.error} />;
  if (deck.isError) return <ErrorState error={deck.error} />;
  if (!activeRun) return <EmptyState label="No deck yet" hint="Run `ytk lsd deck RUN_ID` to write one." />;

  return (
    <main id="main-content" className="mx-auto flex w-full max-w-3xl flex-col gap-4 pb-12">
      <HubControls>
        {runs.data && runs.data.length > 1 && (
          <SegmentedControl label="run" value={activeRun} onValueChange={setRunId}>
            {runs.data.map((r) => (
              <SegmentedControlItem key={r.run_id} value={r.run_id}>
                {r.run_id}
              </SegmentedControlItem>
            ))}
          </SegmentedControl>
        )}
        <span className="font-data text-sm tracking-[0.03em] text-ink2 lowercase" role="status">
          {done} of {cards.length} rated
        </span>
      </HubControls>

      {!current ? (
        <EmptyState label="Deck rated" hint="Run `ytk lsd score` for the gate verdicts." />
      ) : (
        <article className="mx-4 flex flex-col gap-5 rounded-xl border border-line bg-bg1 p-6">
          <header className="flex items-baseline justify-between gap-4">
            <span className="font-data text-xs tracking-[0.08em] text-mute uppercase">{current.kind}</span>
            <span className="font-data text-xs tracking-[0.03em] text-mute lowercase">
              card {revealed ? done : done + 1} of {cards.length}
            </span>
          </header>
          <h1 className="m-0 font-display text-2xl leading-tight text-ink">{current.title}</h1>
          <p className="m-0 text-[0.95rem] leading-relaxed whitespace-pre-line text-ink2">{current.body}</p>

          {!revealed ? (
            <div className="flex flex-col gap-3">
              <SegmentedControl label={QUESTION} value={score} onValueChange={submit}>
                {SCORES.map((s) => (
                  <SegmentedControlItem key={s} value={s} aria-label={`score ${s}`} disabled={rate.isPending}>
                    {s}
                  </SegmentedControlItem>
                ))}
              </SegmentedControl>
              <span className="font-data text-xs tracking-[0.03em] text-mute lowercase">
                1 never thought it · 3 adjacent to something I had · {YES}+ new and it holds. keys 1-5.
              </span>
              <textarea
                aria-label="note"
                placeholder="optional: why"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                className="w-full rounded-md border border-line bg-bg0 p-2 font-data text-sm text-ink"
              />
              {rate.isError && (
                <span role="alert" className="text-sm text-danger">
                  rating failed: {(rate.error as Error).message}
                </span>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-3 border-t border-line pt-4">
              <span className="font-data text-xs tracking-[0.08em] text-mute uppercase">
                scored {score} · made from
              </span>
              <ul className="m-0 flex list-none flex-col gap-1 p-0">
                {current.parents.map((p) => (
                  <li key={p.id} className="text-sm text-ink2">
                    {p.title}
                  </li>
                ))}
              </ul>
              {current.extra?.bridge && <Scaffold label="bridge" text={current.extra.bridge} />}
              {current.extra?.consequence && (
                <Scaffold label="consequence" text={current.extra.consequence} />
              )}
              {current.extra?.question && <Scaffold label="question" text={current.extra.question} />}
              {current.extra?.trail && current.extra.trail.length > 0 && (
                <div className="flex flex-col gap-1">
                  <span className="font-data text-xs tracking-[0.08em] text-mute uppercase">trail</span>
                  <ol className="m-0 flex list-decimal flex-col gap-0.5 pl-5 font-data text-xs text-ink2">
                    {current.extra.trail.map((step, k) => (
                      <li key={k}>{step}</li>
                    ))}
                  </ol>
                </div>
              )}
              <Button onClick={next} className="self-start">
                next
              </Button>
            </div>
          )}
        </article>
      )}
    </main>
  );
}
