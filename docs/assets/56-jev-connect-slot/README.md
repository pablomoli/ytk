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

## Result (run 2026-10-30, `jev-arms.json`, `sonnet-arms.json`, `judged-pairs.json`, `scores.json`)

**Registered loss on B1, B2 and B3. B4 and stability passed.** At the
registered threshold Jev is a strict linker: it refuses everything the owner
struck and everything the shipped model declined, and it also refuses most
of what the owner approved and the readers wanted.

**The ruler.** Three readers (`readers/judge-A.json`, `-B`, `-C`, order in
`readers/key.json`) graded all 81 pairs: median grades 0: 5, 1: 21, 2: 34,
3: 21, so 55 of 81 are link-worthy. Agreement is high: exact match 0.94,
0.95 and 0.99 by reader pair, within one grade 1.00 on all three. That
clears the registered 70% gate and carries a caveat the registration did
not anticipate: the three readers were three sessions of the same model
under the same instructions, so they are correlated, closer to one careful
reader sampled three times than to three independent judges. Against the
owner the readers are stricter: 30 of the 39 approved links are link-worthy
to them, 0 of the 3 struck, 4 of the 15 declined. The nine approved links
they graded 1 are shared-domain links (two Blender notes behind a Shopify
release, two math explainers, two neuroscience notes), the kind the owner
approved in a batch and a reader of the new note would not have asked for.

| arm | yes / 81 | accuracy | precision | recall | F1 | approved kept / 39 | struck dropped / 3 | AUC | median per landed note |
|---|---|---|---|---|---|---|---|---|---|
| rate null, 5th–95th at J1's yes-rate | | 0.395–0.519 | | | | | | | |
| best cosine threshold (0.515, fitted on the answers) | | 0.790 | | | | | | 0.818 | |
| A0 shipped record (Sept–Oct) | 66 | 0.765 | 0.773 | 0.927 | 0.843 | 39 | 0 | | 16 s (ledger) |
| A1 Sonnet replay, adaptive thinking | 53 | 0.753 | 0.830 | 0.800 | 0.815 | 30 | 3 | | 11.1 s API, 13.7 s wall |
| A2 Sonnet, thinking off | 35 | 0.630 | 0.857 | 0.545 | 0.667 | 15 | 3 | | 6.7 s API, 11.0 s wall |
| A3 Sonnet, thinking forced (16k, effort high) | 56 | **0.790** | 0.839 | 0.855 | **0.847** | 32 | 3 | | 21.0 s API, 23.6 s wall, max 113 s |
| **J1 Jev Noul, both bodies (primary)** | **25** | **0.605** | **0.960** | **0.436** | 0.600 | **17** | **3** | **0.920** | **0.18 s**, max 0.35 s |
| J2 Jev Noul, thesis level | 15 | 0.457 | 0.867 | 0.236 | 0.371 | 9 | 1 | 0.721 | 0.13 s |

- **B1, not worse than the incumbent: fail.** J1 0.605 against A1 0.753,
  twelve pairs apart; paired bootstrap on per-pair correctness
  [−0.284, 0.000]. J1 is the most precise arm in the table (24 of its 25
  yeses are link-worthy) and the second worst on recall (24 of 55).
- **B2, the owner's links survive: fail.** 17 of 39 approved kept against
  a bar of 37; 3 of 3 struck dropped.
- **B3, above similarity: fail, narrowly and on one half.** J1's AUC
  0.920 against the cosine's 0.818, a gain of 0.10 whose bootstrap
  interval is [−0.005, +0.222]; the lower bound touches zero, so the bar as
  written is not cleared. The second half passed: accuracy 0.605 against a
  rate-null 95th percentile of 0.519.
- **B4, speed: pass.** Median 0.18 s per landed note, slowest 0.35 s, 29
  requests, 181,904 input tokens, about $0.008. Sixty times faster than the
  shipped call's API time and ninety times faster than its wall time.
- **Stability in decision space: pass.** 20 pairs re-sent, 20 of 20
  decisions unchanged; median |ΔP| 0.010, max 0.05.

**Post hoc, not registered.** The probability ordering is the strongest
thing measured here. At a threshold of 0.14, J1 would keep 37 of 39
approved links, drop 2 of 3 struck, and score 0.815 against the readers,
above every Sonnet arm, including the one that thinks for a thousand
tokens. That number was read off the answers and moves no bar. It says
what a re-registration should ask: whether a threshold chosen on *these*
pairs holds on the next 81. Figure 02's left panel shows the shape: the
grade-0 and grade-1 pairs sit below 0.3 almost without exception, and the
grade-3 pairs that J1 missed at 0.5 are the ones whose link runs through
the owner's project rather than the text (three cagescan references).

**The thinking question (figure 03).** Thinking changes the decision, and
more than expected. With thinking disabled the model links 35 pairs and
scores 0.630; the shipped adaptive setting spends a median 369 tokens,
links 53 and scores 0.753; forced thinking spends a median 1,141 tokens
(max 5,615), links 56 and scores 0.790, the best arm on the blind ruler.
Paired accuracy A3 − A2 [+0.037, +0.284], A1 − A2 [+0.012, +0.235], both
clear of zero on 81 pairs, which the registration said would be unlikely.
The three settings disagree on 29 of 81 pairs. The price is latency: forced
thinking doubles the API time to 21 s median and the slowest call took 96
s. The shipped setting is already the middle of this curve; the ledger's
16 s per connect call was not thinking's cost, and the model with thinking
off is a worse linker, not a cheaper equal.

**Reading.** The registration asked the wrong question of the right
instrument. It asked whether Jev at 0.5 agrees with the readers as often as
Sonnet does, and it does not: Jev's calibrated "yes" means "the same
specific thing" where the readers' and the owner's "yes" means "worth a
link". But the ordering Jev produces separates the grades better than any
arm here can be measured to, and it does so in a fifth of a second with no
clause to write. The failure is the threshold, the owner's project context
that the text does not carry, and the thin reader panel, in that order.

**Decision.** This registration closes as a loss; the connect slot keeps
the generated answer. Two follow-ups are worth their own registration and
neither reopens this one: a held-out threshold test (choose on these 81,
test on the next batch of connect rows as they land, with the owner's
rulings as they come), and a state that carries the owner's project notes
beside the two bodies, since the three grade-3 misses all needed a third
note to see. A third question is the incumbent's: whether the shipped
connect call should set effort high, which this section measured as a
four-point gain for ten more seconds a call and did not register.
