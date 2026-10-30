# 54 — Jev gate replay: does a decision model earn the reranker slot the local model could not?

Rung 1 of the Jev program. Section 53 produced the picture and a measured
shape (on 22 real searches, Jev's Noul over the stored text lifted nDCG@20 from
0.816 to 0.958 against blind full-text grades). This section replays the
retrieval gate's frozen query set through the same arm, with the bars written
down here before the first request was sent.

## Registration (written 2026-10-30, before any call)

**The slot.** #86 measured a second-stage reranker over the production top-30:
Qwen3-Reranker-0.6B lifted hit@1 0.7115 → 0.7949 and hit@5 0.9038 → 0.9359 on
the 156 gate queries, and never shipped on because its median query took
18.6 s against a budget of +1 s per search (`experiments/rerank_bench_results.json`).
The lighter config (depth 10, 512 tokens) ran in 7.7 s and demoted 15 golds out
of the top five while promoting 3. The slot is therefore defined by two
numbers at once: the gain the local model showed, and the latency it missed.

**The arm.** Production search's top-30 for each query (`experiments/rerank_bench.py:retrieve_with_docs`,
the production merge rules with documents kept), each candidate's full stored
document in the state, one Noul per candidate: "Is `candidates.cNN` the note
someone who searched for `query` would open?", criteria as in section 53.
Candidates reordered by the Noul value. Queries whose state exceeds 80k
characters are sent as two requests of 15 (Nouls are absolute, so a split does
not change the ordering). `jev-1.14.0`, pinned. No Choice arm: section 53
showed Noul ≥ Choice on stored text, and Choice's relative probabilities
collapse on every non-winner, which is the wrong shape for a graded ranking.

**Scoring, exactly as the gate scores.** Results outside `frozen_corpus.json`
dropped before ranking, window 10, gold resolved through
`retrieval_gate._live_resolver`. Three arms on the same candidate lists:
served (cosine), Qwen3 depth-30 from the bench rows on disk, Jev Noul. Graded
metric: nDCG@10 over `qrels.json` (4,681 graded pairs on the same queries;
unjudged pairs count as grade 0, disclosed). Null: 1,000 random orderings of
each query's frozen top-30, scored the same way, drawn as the band.

**Bars.** Jev earns the slot only if all three hold:

- B1, gain: hit@1 ≥ 0.79 and hit@5 ≥ 0.93 on the 156 queries (the local
  model's measured numbers, rounded down), scored with the frozen filter.
- B2, speed: median Jev wall time per query ≤ 1.0 s, including a split
  query's second request.
- B3, no silent damage: golds demoted out of the top five ≤ 3 (the gate's
  tolerance of 0.02 on 156 queries), and nDCG@10's paired bootstrap 95%
  interval against served order excludes zero.

Stability (rung 2, tightened from section 53's measurement): 20 queries re-sent
once; median |ΔP| ≤ 0.005 and p90 ≤ 0.03 over their Nouls. A failure here
voids B1–B3, because a threshold in code needs a number that holds still.

**Headroom.** Six of 156 golds sit outside the production top-30 (dry run,
2026-10-30), so no reorder of that list can score above hit@k 0.962. The bars
above sit under that ceiling.

**Cost, estimated before the run.** 156 queries at a median 58k characters of
state (about 15k tokens), roughly 2.3M input tokens, about $0.10; the stability
re-send adds about $0.02. Local compute: one retrieval pass, 27 s.

**What a loss looks like.** If B1 fails, Jev does not reproduce the local
model's gain and the slot stays empty. If B1 passes and B2 fails, the finding
is the same as #86's and nothing changes. If B3 fails on demotions, Jev is the
depth-10 story again: a mean that hides damage. Each is reported with the same
prominence as a pass.

## Result (run 2026-10-30, `rung1.json`, `rung1-scores.json`, `rung1-stability.json`)

**Rung 1 is a registered loss.** B1 failed and the stability bar failed. B2
and B3 passed.

| arm | hit@1 | hit@5 | hit@10 | nDCG@10 |
|---|---|---|---|---|
| shuffle null | 0.045 | 0.227 | 0.434 | 0.369 ± 0.011 |
| served (cosine, today, frozen filter) | 0.712 | 0.897 | 0.936 | 0.658 |
| Qwen3 depth 30 (#86, July, no frozen filter) | 0.795 | 0.936 | 0.974 | — |
| Jev Noul, stored text | **0.776** | **0.917** | 0.942 | **0.757** |
| registered bar | 0.79 | 0.93 | | |

- **B1, gain: fail.** hit@1 0.776 against 0.79, hit@5 0.917 against 0.93.
  Jev recovered about three quarters of the local model's hit@1 gain
  (+0.064 of +0.083) and about half of its hit@5 gain (+0.020 of +0.032).
  Per bucket, Jev matched Qwen3 on segments at hit@1 (0.864) and on memories
  at hit@5 (0.899), and trailed it on videos (0.909 against 0.970).
- **B2, speed: pass.** Median wall time 261 ms, p95 533 ms, slowest query
  939 ms (a split one). 180 requests for 156 queries (24 split), 2,485,944
  input tokens, $0.104.
- **B3, damage: pass.** 3 golds demoted out of the top five against 6
  promoted in; 25 moved up, 16 down, 115 unchanged. nDCG@10 Jev 0.757 against
  served 0.658, wins 117 / ties 7 / losses 32, paired mean +0.099, bootstrap
  95% [+0.078, +0.123].
- **Stability: fail as registered.** 20 queries re-sent, 600 Nouls: median
  |ΔP| 0.010 against the bar's 0.005, p90 0.030 at the bar, max 0.09. The bar
  was set from section 53's snippet runs (median 0.000); full-text states at
  15k tokens jitter more. *Post hoc, not registered:* the jitter changed the
  frozen top-1 in 2 of 20 queries and the gold's rank in 2 of 20; no query
  kept an identical top-10 order. A bar on the number was the wrong
  instrument for a ranking; a bar in rank space would have read 18/20. That
  observation does not move this section's bar.

Figures: `01-rank-shift.png`, gold rank served → Jev and served → Qwen3 on
one axis, with hit@k against the registered bars and the per-k null;
`02-graded-and-time.png`, nDCG@10 per bucket against the null, and wall time
per query against the budget.

**Caveats.** Served order today scores hit@5 0.897 where the stamped baseline
says 0.904: the frozen-filtered live store has drifted inside the gate's own
0.02 tolerance, so Jev was scored on today's lists while the bar came from
July's. Qwen3's numbers are from July's candidate lists without the frozen
filter; the registration accepted that and the bar inherited it. The bench
rows on disk hold only the gold's rank, so Qwen3 has no graded score here.
Unjudged qrels pairs count as grade 0, which penalises every arm equally.

**What this does and does not say.** Against served order, inside the
budget, Jev is a clear improvement by every measure here, with the damage
check passed. Against the bar this section chose, the local model's measured
gain, it fell 1.4 and 1.3 points short. The slot stays empty on this
registration.

## Decision (2026-10-30, the agent's, recorded with its reasons; the owner may overrule)

**Rung 1 closes as a loss. The bars stand. Jev does not enter the reranker
slot on this evidence, and nothing is re-registered on these 156 queries.**

The question the loss raised was whether a bar borrowed from a model that
cannot run inside the budget was the right bar. One more measurement answers
it without touching section 54's bars. The retrieval gate (#85) treats a
change on its gated metrics, hit@5 and hit@10, as real only above its
tolerance of 0.02 (`ytk/retrieval_gate.py`, `_GATED_METRICS`,
`_DEFAULT_TOLERANCE`). Jev's gains on today's lists are hit@5 +0.019 and
hit@10 +0.006. Both sit inside the gate's own noise floor. The gains that are
unmistakable, hit@1 +0.064 and nDCG@10 +0.099 with an interval clear of zero,
are on metrics the gate does not gate on. So the production-facing bar
("beat served order inside the budget, by at least what the gate calls a
change") fails as well, and a bar set now that Jev would pass would be a bar
set with the answer in view. The only instrument guarding search would not
be able to see the improvement it shipped.

What the program keeps from rungs 0 and 1: the stored document is the right
context and the snippet is not; the Noul is near-deterministic in rank space
(18/20) though not in its third decimal; latency is a quarter of the budget;
abstention on absent items was clean in section 53; Jev reorders the
production top-30 well short of the local model on known-item hit@k and well
clear of served order on graded relevance.

Follow-ups, each a new question with its own registration, tracked in #219:

1. A different arm against the *same* bars as section 54: title fields
   beside the text, MemSearch's stricter wording ("states the specific fact,
   not a similar topic"), a Noul gated by a Choice's abstention. A new arm may
   clear the standing bars honestly; the bars do not move to meet it.
2. A stability bar in rank space (gold rank and frozen top-1 unchanged on
   re-send), registered before the run, on queries not used here.
3. The slots section 53 pointed at that are not this one: abstention
   ("nothing here") on the id-lookup path, and connect's per-candidate
   judgment, each with its own baseline and null.
4. Whether the gate should gate on a graded metric at all is a change to the
   gate, argued in its own section under #85, never as a way to pass this one.
