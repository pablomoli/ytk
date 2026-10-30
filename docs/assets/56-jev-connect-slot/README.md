# 56 — The connect slot: can a typed decision replace the linker's judgment?

Rung 4 of the Jev program, follow-up 4 of #219. When a note lands, `connect`
gathers up to five candidate neighbours and asks Sonnet, in one call, which
of them deserve a link and why (`ytk/connect.py`, `_argue`). The owner then
approves, strikes some, or rejects the proposal in the hub. This section asks
whether the *decision* half of that call, which candidates survive, can be
made by a Noul per pair instead of a generated answer, with the clause written
afterwards only for survivors. It does not ask whether Jev can write the
clause; it cannot, and the clause has a job on the surface.

Figure 01 is the record before any arm ran: every candidate pair the linker
has seen, by today's note-to-note cosine, coloured by what shipped and what
the owner ruled.

## What the ledger holds (2026-10-30, `pairs.json`)

| | count |
|---|---|
| landed notes with a connect decision on record | 29 |
| candidate pairs | 81 |
| argued by the shipped model | 66 |
| declined by the shipped model (identities logged only since 2026-10-24) | 15 |
| approved by the owner | 39 |
| struck by the owner | 3 |
| awaiting the owner's ruling in the hub | 39 |

Two facts about the incumbent, measured before registration. First, the
shipped call is `claude-sonnet-5` through the Agent SDK with thinking left at
the SDK default, which is adaptive: a five-call probe on one connect prompt
showed 0 to 117 thinking tokens per call, the same single link chosen every
time, and 5.5 to 9.2 s of API time inside 10.6 to 12.5 s of wall time. The
ledger's 16 s mean per connect call is mostly SDK start-up, not thought.
Second, cosine does not explain the decision: argued and declined candidates
overlap on today's cosine (medians 0.56 and 0.47, ranges 0.36–0.90 and
0.35–0.59), so the model is doing something a threshold would not.

## Registration (written 2026-10-30, before any arm call)

**Universe.** The 81 pairs in `pairs.json`. Nothing is added or dropped
after this line. Each pair is judged as (new note, candidate), the direction
the linker writes.

**Ruler 1, blind grades.** Three fresh readers, no shared context, each
reads both notes' full bodies (everything above the raw transcript, with the
`## Connections` section and every wikilink removed so a link already written
cannot leak) in one seeded shuffle, with no shipped decision, ruling or cosine
visible. Grade per pair: 0 unrelated; 1 same broad topic only; 2 worth a link,
a reader of the new note would want the candidate; 3 the same specific thing,
event, paper, person or claim. The pair's grade is the median of three.
*Link-worthy* means median ≥ 2. Reader agreement is reported (pairwise exact
and within one grade) before any arm is scored; if two readers agree within
one grade on fewer than 70% of pairs the ruler is declared too soft and the
section reports that instead of a verdict.

**Ruler 2, the owner.** The 42 ruled pairs: 39 approved (the link was
written) and 3 struck (proposed, not written). The 39 pending pairs are not
solicited for this section.

**Arms.** Every arm answers yes or no per pair.

- A0, the shipped record: argued or declined, from the ledger. Reference,
  not a fresh run.
- A1, Sonnet replay: the shipped system prompt and schema, the shipped
  user-prompt format, `claude-sonnet-5`, SDK default thinking (adaptive).
  Where the ledger did not log a candidate's "matched on" field (the 42
  pre-October pairs) the field reads `not logged`, disclosed. One call per
  landed note, as shipped.
- A2, Sonnet with thinking disabled. Same prompt.
- A3, Sonnet with thinking enabled, budget 16,000 tokens, effort high. Same
  prompt. A budget is a ceiling the model may ignore (the probe used 100 of
  4,096), so effort is set as well; thinking tokens actually used are
  reported per call.
- J1, Jev Noul over the two bodies (primary): one Noul per pair, state holds
  the new note's title and body and the candidate's title and body, question
  "Should `new_note` carry a link to `candidate`?", true: "A reader of the new
  note would want the candidate: the same specific thing, event, paper,
  person or claim, or a claim that directly extends or contradicts it.",
  false: "The same broad topic only, a passing mention, or nothing related."
  Decision: P ≥ 0.5. Candidates of one landed note share one request
  (Nouls are independent); a request over 80,000 characters is split.
  `jev-1.14.0`, pinned.
- J2, Jev Noul at the incumbent's information level (secondary): the same
  question over the new note's thesis and summary and the candidate's title
  and thesis, the fields Sonnet sees. Reported, no verdict.

**Scoring.** Against ruler 1: accuracy (agreement with link-worthy),
precision, recall and F1 on link-worthy pairs, and for J1 and J2 the AUC of
the Noul probability against the grade. Against ruler 2: approved pairs the
arm would keep (of 39) and struck pairs it would drop (of 3). Paired
comparisons are bootstrap intervals (1,000 resamples over pairs) on the
per-pair difference in correctness.

**Nulls.** Two, drawn on the same axis as the arms. A cosine rule: the
threshold on today's note-to-note cosine that maximises accuracy against
ruler 1, which is the best any similarity-only rule could do and is fitted
on the answers, so it is an optimistic null. A rate null: 1,000 random
yes/no assignments at each arm's own yes-rate, scored the same way.

**Bars, on J1 only.**

- B1, not worse than the incumbent: J1's accuracy against ruler 1 is within
  four pairs of A1's (5% of 81) or above it, and the paired bootstrap 95%
  interval on the accuracy difference does not lie entirely below −0.05.
- B2, the owner's links survive: J1 says yes on at least 37 of the 39
  approved pairs and no on at least 2 of the 3 struck.
- B3, above similarity: J1's AUC exceeds the cosine's AUC against ruler 1
  with a bootstrap 95% interval on the difference clear of zero, and J1's
  accuracy exceeds the 95th percentile of its rate null.
- B4, speed: median Jev wall time per landed note (all its candidates,
  splits included) ≤ 1.0 s.
- Stability, in decision space: 20 pairs re-sent once; the yes/no decision
  unchanged on ≥ 19 of 20.

**The thinking question.** A2 against A3 (off against forced on) and A1
against A2 (adaptive against off): paired accuracy difference with its
interval, and thinking tokens used. Reported as measured, no bar: with 81
pairs, a difference of two or three pairs will sit inside its own interval,
and the section will say so rather than call it a result.

**Verdict rule.** Jev takes the decision in the connect slot, with Sonnet
writing clauses for survivors only, if and only if B1–B4 and the stability
bar hold on J1. J2, A2 and A3 carry no verdict. A loss on any bar is reported
with the same prominence as a pass and closes this registration; a new arm
is a new section.

**Power, disclosed.** 81 pairs, 42 of them ruled by the owner and 3 of
those struck. A five-point accuracy difference is four pairs. The owner
ruler can confirm that approved links survive; with three strikes it cannot
measure false positives, which is why ruler 1 exists and carries B1 and B3.

**Cost, estimated before the run.** J1: about 29 requests over roughly 640k
characters of note bodies, under 200k tokens, about $0.01; J2 and the
re-send add less. Sonnet arms: 87 calls on the subscription, about 15
minutes of wall time with concurrency. Readers: three agent sessions over
950k characters of sheets.

**What a loss looks like.** If B2 fails, Jev would drop links the owner
wanted, and no accuracy number compensates. If B3 fails, Jev is a cosine
threshold with a price. If B1 fails with B2–B4 passing, the typed decision
is cheaper and faster and reads the pairs worse than the incumbent, and the
slot keeps the generated answer.
