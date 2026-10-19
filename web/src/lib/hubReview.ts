import type { HubCandidate, HubVerdict, HubVerdictChange } from "../api/hubs";

export type HubFilter = "pending" | "approve" | "strike" | "all";
export type HubDraft = Record<string, HubVerdict>;

export const hubId = (c: Pick<HubCandidate, "kind" | "key">) => `${c.kind}:${c.key}`;

/** Draft decisions that differ from the recorded verdict; pending stays unsent. */
export function changedVerdicts(candidates: HubCandidate[], draft: HubDraft): HubVerdictChange[] {
  const out: HubVerdictChange[] = [];
  for (const c of candidates) {
    const next = draft[hubId(c)];
    if (next && next !== c.verdict) out.push({ kind: c.kind, key: c.key, verdict: next });
  }
  return out;
}

/** Filters on the recorded verdict, so a row stays put while it is being decided. */
export function filterCandidates(candidates: HubCandidate[], filter: HubFilter): HubCandidate[] {
  return filter === "all" ? candidates : candidates.filter((c) => c.verdict === filter);
}

/** Marks every undecided pending row as approved; struck and decided rows keep their state. */
export function approvePending(shown: HubCandidate[], draft: HubDraft): HubDraft {
  const next = { ...draft };
  for (const c of shown) if (c.verdict === "pending" && !next[hubId(c)]) next[hubId(c)] = "approve";
  return next;
}
