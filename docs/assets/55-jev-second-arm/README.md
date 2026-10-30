# 55 — Jev, second arm: a different reranker against section 54's standing bars

Rung 1, second attempt. Section 54 registered three bars for the reranker
slot and lost on the first (hit@1 0.776 against 0.79, hit@5 0.917 against
0.93) and on a stability bar written on the wrong quantity. Its bars stand;
nothing in this section edits that result. This is follow-up 1 of #219: a
different arm, registered here before the first request, judged against the
same bars.

## Registration (written 2026-10-30, before any call)

**What changes, and why each change is allowed.** Three things the section 54
arm did not have, each named in section 53 or 54 before this registration:

1. A title field beside each candidate's stored text (section 53 round two
   sent text only; memory documents begin with their heading but video and
   segment documents do not carry their title). Videos and segments take
   the stored `title` metadata; memory notes take the filename stem of
   `source_path`.
2. Stricter wording, after MemSearch's prompt that rejects "merely a similar
   topic": "Does `candidates.cNN` hold the specific thing `query` asks for,
   not merely a similar topic?", true: "Its title or text names the specific
   item, decision, session, person or fact in `query`.", false: "The same
   project or topic only, a different item, or nothing related."
3. Fusion with the first stage. The primary arm orders candidates by
   reciprocal rank fusion of served rank and Noul rank, k = 60, the standard
   constant, no tuning: score = 1/(60 + r_served) + 1/(60 + r_noul), ties
   broken by served order. Section 54 threw the first stage's order away and
   let the Noul alone decide; a reranker that keeps the retriever's vote is
   the common shape, and k = 60 is fixed in the literature rather than fitted
   here.

**Arms.** Primary: RRF of served and the new Noul (title + text + wording).
Secondary, reported but carrying no verdict: the new Noul alone. Section 54's
Noul and the July Qwen3 ranks are drawn beside them for reference from disk.

**Scoring.** Exactly section 54's: production top-30, frozen filter, window
10, gold through `retrieval_gate._live_resolver`; nDCG@10 over `qrels.json`
with unjudged pairs at grade 0; 1,000 random orderings per query as the null.

**Bars, identical to section 54's B1–B3, on the primary arm only.**

- B1, gain: hit@1 ≥ 0.79 and hit@5 ≥ 0.93.
- B2, speed: median Jev wall time per query ≤ 1.0 s.
- B3, no silent damage: golds demoted out of the top five ≤ 3; nDCG@10's
  paired bootstrap 95% interval against served order excludes zero.

**Stability, now in rank space** (section 54 measured it on the probability
and found that the wrong instrument): 20 queries drawn from the 136 that
section 54 did not re-send, re-sent once; the primary arm's frozen top-1
unchanged in ≥ 18 of 20, and the gold's frozen rank unchanged in ≥ 18 of 20.

**Verdict rule.** Rung 1 passes on this section only if the primary arm
clears B1, B2, B3 and the stability bar. Two arms are measured; one carries
the verdict, chosen here, so a secondary pass is not a pass.

**What a pass or a loss means.** A pass puts a Jev-based second stage behind
the slot's standing bars with the first stage's vote kept; it does not turn
section 54 into anything but the loss it was. A loss closes rung 1 for good
on the local model's gain as the bar, and the remaining #219 items are
different questions. Cost estimate: about $0.12 for the pass plus $0.02 for
the re-send.

## Result (run 2026-10-30, `rung1b.json`, `rung1b-scores.json`, `rung1b-stability.json`)

**Rung 1 is a registered loss for the second time, on hit@1 alone.** B1
failed; B2, B3 and the rank-space stability bar passed.

| arm | hit@1 | hit@5 | hit@10 | nDCG@10 | vs served: wins/ties/losses | demoted / promoted |
|---|---|---|---|---|---|---|
| shuffle null | 0.045 | 0.228 | 0.437 | 0.370 ± 0.012 | | |
| served (cosine, today) | 0.712 | 0.897 | 0.936 | 0.658 | | |
| section 54's Noul (reference) | 0.776 | 0.917 | 0.942 | 0.757 | 117/7/32 | 3 / 6 |
| Qwen3 depth 30 (#86, July, reference) | 0.795 | 0.936 | 0.974 | — | | |
| **primary: fused (RRF k=60)** | **0.750** | **0.936** | 0.942 | 0.730 | 119/17/20, +0.072 [+0.059, +0.086] | **0 / 6** |
| secondary: new Noul alone | 0.769 | 0.936 | 0.955 | 0.755 | 115/9/32, +0.097 [+0.075, +0.119] | 1 / 7 |
| registered bar | 0.79 | 0.93 | | | interval clear of zero | ≤ 3 |

- **B1, gain: fail.** The fused arm reaches the local model's hit@5 exactly
  (0.936) and misses hit@1 by four points (0.750 against 0.79). Fusion did
  what fusion does: it kept the first stage's vote, which protected every
  gold already in the top five (zero demoted) and held back the ones the
  Noul alone would have promoted to first. The Noul alone, with titles and
  the stricter wording, is the best Jev arm measured so far on hit@5 and
  hit@10 (0.936, 0.955) and still misses hit@1 (0.769). It carries no verdict.
- **B2, speed: pass.** Median 318 ms, p95 568 ms, slowest 643 ms; 180
  requests, titles added about 2% to the tokens.
- **B3, damage: pass**, and cleanly: 0 golds demoted out of the top five
  against 6 promoted in; nDCG@10 paired gain +0.072 [+0.059, +0.086].
- **Stability in rank space: pass.** 20 fresh queries re-sent: the fused
  arm's frozen top-1 unchanged 20 of 20, the gold's frozen rank unchanged 19
  of 20, against a bar of 18. The probability jitter section 54 measured
  does not reach the order that ships.

Figure: `01-rank-shift.png`, gold rank served → fused, served → new Noul,
served → section 54's Noul on one axis; hit@k for all arms against the
standing bars and the per-k null.

**Reading.** Two registered arms, two losses, both on hit@1 and nothing
else. Every other bar the slot was given has now been passed by a Jev arm:
hit@5 at the local model's number, speed at a third of the budget, zero
demotions, stable orderings. What Jev does not do on this corpus is put the
known item first as often as the local cross-encoder did in July. That is a
finding, and it is final for this bar: no third arm is registered, because a
third draw against the same number on the same 156 queries would be a search
for a pass rather than a measurement.

**Decision.** Rung 1 closes on the local model's gain as the bar, lost. The
record holds two losses that say precisely what the gap is: four points of
hit@1 for the safe arm, two for the sharp one. Whether the slot should be
judged on hit@1 at all, when the gate itself gates on hit@5 and hit@10 and
both now clear, is a question about the gate and the slot, listed in #219,
and it is the owner's.

**Owner's ruling (2026-10-30): the loss is accepted.** Rung 1 is closed on
the local model's gain as the bar; sections 54 and 55 stand as written; no
re-registration on these queries. The remaining #219 items (abstention slot,
connect slot, rank-space stability as a standing bar, the gate-metric
question) are separate registrations for another day.
