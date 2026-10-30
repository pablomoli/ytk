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
