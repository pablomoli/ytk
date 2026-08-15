# 39 — The trace inventory

First rung of #96: before defining any telemetry schema, inventory every trace
the second brain already leaves and see what it can and cannot answer. The
issue's ordering is deliberate — retrofit semantics onto real traces first, so
the missing events reveal themselves instead of being guessed. This section is
that retrofit, and the first version of the acceptance report ("what was
captured, what became a thought, what was retrieved and by whom, what was
reused, where retrieval failed").

## The census

| trace | rows | window | what it holds | what it cannot say |
|---|---|---|---|---|
| `~/.ytk/retrieval_log.jsonl` (#150 A4) | 60,425 | 07-29 → | every served search result: ts, surface, query, doc, rank, distance | who asked; zero-result searches (never logged — `store.py` returns before writing); which session |
| `~/.ytk/logs/search.jsonl` | **2** | 07-17 → | user-typed hub searches, verbatim | anything — two rows exist |
| `~/.ytk/capture_log.jsonl` | 585 | 07-29 → | capture attempts: surface (hub/feed/sync), source, outcome | user intent vs bulk drain (08-04 alone holds 344 — a queue sweep, not a reading day) |
| claude-mem db | 32.5k obs, 2,356 sessions (872 ytk) | 02-04 → | `files_read` per observation — vault notes actually opened inside work sessions | globs are lossy (`sources/youtube/*.md (395 files)` collapses a session-wide scan into one string) |
| interest snapshots | 23 | 06-02 → | themes, weights, and — since #83 — stamped lifecycle events (47 birth, 36 merge, 18 split, 11 death, 9 restated) | attention vs capture volume (that distinction is this issue's job) |
| session briefs | 57 | — | hard citations of what knowledge fed what work | not yet parsed; next rung |
| store (Chroma) | 671 notes | — | embeddings, `captured_at` 100% coverage | nothing about use |

## Figure 01 — what the retrieval log actually holds

The 2,302 search events classify, layer by layer, into: 1,904 eval-gate
replays (the frozen #85 query set exercising the production path), 152
programmatic bursts (recall harnesses, the e2 set, and one 08-10 sweep that
searches by note *thesis sentences* — pipeline traffic), 137 recurring
smoke-test probes, 76 unit-test fixtures — and **33 genuine searches in 15
days**. 98.6% of the only retrieval trace on disk is the system examining
itself. The residue: 21 events fall inside claude-mem session windows
(agent), the other 12 are session-shaped but unmatched (the window join is
conservative), and **zero** came from the hub. The two hub searches ever
typed predate the log.

## Figure 02 — the one-sided loop

Capture runs at 585 events for the window (554 through the hub; the 08-04
spike is a bulk queue drain, disclosed, not a reading binge) against 33
genuine searches: 18:1. Of 671 embedded notes, 55 were ever served to a
genuine search in the window; 153 were read inside Claude sessions across all
time — the agent loop reaches ~3x more of the corpus through `vault_read`
than through search, **and none of those reads are logged by ytk** —
claude-mem observes them by accident.

## The acceptance questions, answered as far as the traces allow

- **What was captured:** 585 capture events over 16 days, 94% via hub, 6.3%
  errors (37 — pipeline-health number).
- **What became a thought:** 32 notes carry an authored-thought signal
  (r >= 2) — 5% of the corpus (snapshot `signal_counts`).
- **What was retrieved, by whom:** 33 genuine searches — 21 agent-confirmed,
  12 session-shaped, 0 human-typed. Plus 153 distinct notes read in sessions,
  invisible to ytk's own logs.
- **What was reused:** answerable only through session briefs and claude-mem
  citations; not yet parsed. Next rung.
- **Where retrieval failed:** unmeasurable. Zero-result searches are never
  written; abandonment and reformulation are nearly invisible (3 chains
  detectable). The failure signal the issue most wants does not exist yet.
- **Ready for synthesis:** not derivable from these traces; needs the
  thoughts/annotation layer. Next rung.

## What the vocabulary must add (found, not guessed)

1. **`actor` needs three values, not two** — `user | agent | system`. The
   thesis-sentence sweeps, recall harnesses, and eval replays are real
   traffic from neither the user nor a working agent; unlabeled, they are
   93% of the log and drown everything.
2. **Zero-result logging** — one-line change in `log_retrieval`; without it
   the recall-failure metrics of #96 have no substrate.
3. **`vault_read` events** — the agent's dominant access path is entirely
   unlogged by ytk; the strongest evidence source exists only as claude-mem
   exhaust with lossy globs.
4. **Session id on retrieval events** — the window join works but is
   conservative; a passed-through session id would make the actor split
   exact.
5. **Instrument traffic must self-identify** — `YTK_RETRIEVAL_LOG=off`
   exists and the eval gate does not set it. Tagging at write time beats
   forensic classification (this section is the proof: the classifier took
   more work than the flag would have).

## Limits

- The actor split under-attributes agents: several "ambiguous" events are
  recognizably session-shaped work whose sessions the window join missed.
- claude-mem `files_read` undercounts: glob summaries collapse whole-corpus
  scans; 153 distinct notes is a floor, not a measurement.
- The window is 15 days of retrieval against 6 months of sessions; ratios
  compare only inside the shared window.
- Failure anecdotes (the issue's first checkbox) are not here: candidates can
  be mined, but the anchoring stories are the owner's to tell.

Compute: `experiments/trace_inventory.py` →
`trace_inventory_results.json` (commit-stamped). Figures:
`scripts/plot_trace_inventory.py`.
