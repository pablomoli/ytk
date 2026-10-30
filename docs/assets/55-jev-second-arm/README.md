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
