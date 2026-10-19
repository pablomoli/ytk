import { useMemo, useState } from "react";
import { useApplyHubVerdicts, useHubList, type HubCandidate } from "../api/hubs";
import {
  approvePending,
  changedVerdicts,
  filterCandidates,
  hubId,
  type HubDraft,
  type HubFilter,
} from "../lib/hubReview";
import { ConfirmDialog } from "./ConfirmDialog";
import { Button } from "./ui/button";
import { SegmentedControl, SegmentedControlItem } from "./ui/segmented-control";

const FILTERS: { value: HubFilter; label: string }[] = [
  { value: "pending", label: "pending" },
  { value: "approve", label: "approved" },
  { value: "strike", label: "struck" },
  { value: "all", label: "all" },
];

function targetLine(c: HubCandidate): string {
  if (c.hand_made) {
    const also = c.collision ? `; the same name also exists at ${c.collision}` : "";
    return `links to your note ${c.target_path}${also}`;
  }
  const clash = c.collision ? `, renamed because ${c.collision} exists` : "";
  return `new hub [[${c.target}]]${clash}`;
}

export function HubReview() {
  const list = useHubList();
  const apply = useApplyHubVerdicts();
  const [filter, setFilter] = useState<HubFilter>("pending");
  const [draft, setDraft] = useState<HubDraft>({});
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState("");

  const candidates = useMemo(() => list.data?.candidates ?? [], [list.data]);
  const shown = useMemo(() => filterCandidates(candidates, filter), [candidates, filter]);
  const changes = useMemo(() => changedVerdicts(candidates, draft), [candidates, draft]);
  const approving = changes.filter((c) => c.verdict === "approve").length;
  const striking = changes.length - approving;
  const pendingShown = shown.some((c) => c.verdict === "pending" && !draft[hubId(c)]);

  const submit = () => {
    setConfirming(false);
    apply.mutate(changes, {
      onSuccess: (result) => {
        setDraft({});
        setMessage(
          `applied: ${result.recorded} verdicts recorded, ${result.notes_changed} notes rewritten, ${result.hubs_written} hubs written, ${result.hubs_removed} removed`,
        );
      },
      onError: (error) => setMessage(`apply failed: ${String(error)}`),
    });
  };

  const summary = list.data?.summary;

  return (
    <section
      aria-labelledby="hub-links-heading"
      className="flex flex-col gap-4 border-t border-line pt-6"
    >
      <header className="max-w-2xl">
        <h2 id="hub-links-heading" className="m-0 font-serif text-2xl font-normal text-ink">
          Hub links
        </h2>
        <p className="mt-3 text-base leading-7 text-ink2">
          Creators and Key Concept names that appear in {list.data?.threshold ?? 2} or more notes.
          Approved names link every matching note to one hub; striking a name later removes all of
          its links. Nothing is written for a name still pending.
        </p>
        {summary ? (
          <p className="mt-2 font-data text-sm text-mute">
            {summary.concept.names} concepts over {summary.concept.notes} notes,{" "}
            {summary.creator.names} creators over {summary.creator.notes} notes;{" "}
            {summary.concept.pending + summary.creator.pending} pending
          </p>
        ) : null}
      </header>
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="show"
          value={filter}
          onValueChange={(v) => setFilter(v as HubFilter)}
        >
          {FILTERS.map((f) => (
            <SegmentedControlItem key={f.value} value={f.value}>
              {f.label}
            </SegmentedControlItem>
          ))}
        </SegmentedControl>
        <Button
          variant="secondary"
          disabled={!pendingShown}
          onClick={() => setDraft((d) => approvePending(shown, d))}
        >
          Approve pending shown
        </Button>
      </div>
      {list.isError ? (
        <p role="alert" className="text-live">
          {String(list.error)}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="m-0 text-sm text-mute">
          {message}
        </p>
      ) : null}
      {list.isPending ? <p className="text-sm text-mute">Reading source notes.</p> : null}
      {list.data && !shown.length ? (
        <p className="text-sm text-mute">No names in this view.</p>
      ) : null}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {shown.map((c) => {
          const id = hubId(c);
          const choice = draft[id] ?? (c.verdict === "pending" ? "" : c.verdict);
          const struck = choice === "strike";
          return (
            <li
              key={id}
              aria-label={`${c.kind} ${c.name}`}
              className={`flex flex-wrap items-start justify-between gap-3 rounded-card border p-3 ${struck ? "border-line/60 bg-bg1/60 opacity-70" : "border-line bg-bg1"}`}
            >
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-data text-base text-ink">{c.name}</span>
                  <span className="font-data text-xs tracking-[0.08em] text-mute uppercase">
                    {c.kind}
                  </span>
                  <span className="font-data text-sm text-ink2">{c.count} notes</span>
                  {draft[id] && draft[id] !== c.verdict ? (
                    <span className="font-data text-xs text-accent">changed</span>
                  ) : null}
                </div>
                <p className="m-0 truncate text-sm text-ink2">{c.examples.join(" · ")}</p>
                <p className="m-0 text-xs text-mute">{targetLine(c)}</p>
              </div>
              <SegmentedControl
                label={`Verdict for ${c.name}`}
                hideLabel
                value={choice}
                onValueChange={(v) => setDraft((d) => ({ ...d, [id]: v as "approve" | "strike" }))}
              >
                <SegmentedControlItem value="approve">approve</SegmentedControlItem>
                <SegmentedControlItem value="strike">strike</SegmentedControlItem>
              </SegmentedControl>
            </li>
          );
        })}
      </ul>
      {changes.length ? (
        <div className="sticky bottom-0 flex flex-wrap items-center gap-3 border-t border-line bg-bg1 px-4 py-3">
          <Button onClick={() => setConfirming(true)} disabled={apply.isPending}>
            Apply hub list
          </Button>
          <span className="text-sm text-mute">
            {approving} to approve, {striking} to strike
          </span>
          <Button variant="ghost" onClick={() => setDraft({})} disabled={apply.isPending}>
            Clear changes
          </Button>
        </div>
      ) : null}
      {confirming ? (
        <ConfirmDialog
          message={`Record ${changes.length} verdicts and rewrite hub links? ${approving} names gain links, ${striking} lose theirs.`}
          confirmLabel="Apply hub list"
          onConfirm={submit}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
    </section>
  );
}
