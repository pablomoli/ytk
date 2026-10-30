# 57 — Jev at the grader's door: a bouncer before the Opus grade

Follow-up to the Jev program (sections 53–56, #219). Sections 54 and 55
closed the reranker slot as a loss; section 56 closed the connect slot at the
registered threshold. This section asks a different kind of question. The
earlier slots asked Jev to be the final word against a stronger incumbent.
Here Jev is asked to be a bouncer: a fast yes-or-no in front of the grader,
with the grader still the final word on anything the bouncer lets through.

## The slot

The curator grades every draft (`ytk/curator.py`). The order today: the
house-rule lint (`writer_rules.lint`, two of thirteen rules wired, no model),
the deterministic checks (`grader.deterministic_checks`: near-duplicate, take
response, unit cites), then one Opus call (`grader.grade_model`,
`claude-opus-5`) with the rubric, the packet, the attempt header and the
draft, returning pass or a list of bounces by rubric section. A bounce sends
the draft back to the writer (one Sonnet call) for another round; the second
bounce raises the "grader bounce, twice" ask to the owner.

The record (`01-the-graders-bill.png`, drawn from `~/.ytk/ledger.db` with no
model calls): 34 items graded by the model layer, 98 Opus grades totalling 94
minutes at 58 s mean, 134 Sonnet drafts totalling 93 minutes at 42 s mean,
median three grades per item and nine at most. 13 passes, 85 bounces, 31 more
bounces caught by the free layer. The owner ruled on 59 double bounces: 24
"accept as is", 34 "say what is wrong", 1 drop. Grounding is the section the
grader bounces on most and the one the owner overrules most (9 of 25 rulings
whose preceding bounce named it).

The eleven house rules that regex could not express fell through to the Opus
call. A bouncer that judges prose rules at lint speed would complete the free
layer the way it was designed, and every bounce it catches is one Opus call
(58 s) and one of the item's eight calls not spent.

## Registration (written 2026-10-30, before any Jev call)

**Universe.** Every Opus grade in the ledger: 98 grades on 34 items, each a
tuple of draft (`~/.ytk/evidence/drafts/<item>-<n>.json`), packet, attempt
header and Opus verdict (the `activity` row's detail, section names in
`bounces[].check`). Packets: 63 resolve by the recorded `view_hash`, 9 by the
item's latest stored view (the recorded hash is not on disk), 26 are rebuilt
in memory from the bundle at `~/.ytk/evidence/<item>.json` with today's
default budget, the precedent set in `docs/design/linking/README.md` for
drafts graded before packets existed (items 756, 759, 761, 762). Attempt
headers exist for 63 grades; the other 35 get a header with no findings.
Each group is reported separately where it matters. Jev receives the
packet's rendered text only; Opus could open frames. Sections that depend on
frames (Visual sources, frame cites) are at a disadvantage and are reported
by section.

**State and questions.** One System One request per draft. State:
`{"rubric": <~/.ytk/rubric.md>, "house_rules": <writer_rules.HOUSE_RULES>,
"packet": <view.rendered>, "attempt": <attempt header>, "draft": <draft
JSON>}`. If the state exceeds 80,000 characters (the largest size section 56
sent), the packet's transcript tail is cut to fit and the draft is flagged
`cut`. Questions, all Noul, all in the one request:

- `s_<section>` for each judged rubric section: Thesis, Summary, Response to
  my take, Key concepts, Insights, Key moments, Visual sources, Grounding,
  Tags, What I do not want, What I enjoy reading. "Does `draft` fall short of
  rubric section `rubric.<section>`, judged by that section's own words
  against `packet`?" true: "The draft fails what the section asks; a grader
  reading this section would bounce the draft on it." false: "The draft
  meets the section, or the section does not apply to this item." Connections
  is excluded: the rubric says never bounce for it. Exemplars and Who this is
  for are preamble.
- `h_<n>` for each of the 13 house rules: "Does `draft` break house rule
  `house_rules.<n>`?" true: "A sentence in the draft does what the rule
  rejects." false: "No sentence does, or the rule does not apply."

**Arms.** Primary, J-rubric: the eleven section questions; the bouncer blocks
a draft when any section's P ≥ θ, and names the highest section as the
finding. Secondary, J-house: the thirteen rule questions, same block rule,
reported with no verdict. θ = 0.8 is registered as the operating threshold
(a bouncer must be precise; a false block costs a 42 s writer round and one
of eight calls). The full curve over θ is drawn, and any other threshold is
post hoc.

**Rulers.** (1) Opus's verdict on the same draft: pass or bounce, and the set
of bounced sections. (2) The owner's rulings: for each of the 59 answered
"grader bounce, twice" asks, the Opus grade immediately before it is the
draft the owner saw; "accept as is" labels it should-pass, "say what is
wrong" and "drop" label it should-block. Opus blocked all 59 by construction,
so Opus's accuracy on this ruler is 35/59 = 0.593.

**Nulls.** Rate null: Jev's block decisions shuffled across drafts (1,000
draws), scored on both rulers. Lint baseline: the two wired regex rules found
nothing on these drafts by construction (a lint hit never reaches Opus), so
the free layer's catch rate on this universe is 0.

**Bars, on J-rubric at θ = 0.8.**

- B1, safety: of the 13 drafts Opus passed, the bouncer blocks at most 1.
- B2, worth: of the 85 drafts Opus bounced, the bouncer blocks at least 28
  (one third), and in at least two thirds of its blocks the section it names
  is one Opus also named.
- B3, the owner's ruler: accuracy on the 59 rulings above 0.593, with the
  1,000-draw bootstrap 95% interval over rulings clear of 0.593.
- B4, speed: median wall time per draft, all 24 questions in one request,
  at most 2.0 s.
- Stability: 20 drafts re-sent once; the block decision at θ unchanged in at
  least 18, and the named section unchanged in at least 18 of those blocked.

**Verdict rule.** Two verdicts, stated apart. *Worth wiring*: B1, B2, B4 and
stability all pass; this is the performance claim, and it is what would put
Jev in the free layer behind the lint. *Sides with the owner*: B3 passes;
this is the accuracy claim, measured on the only labels the owner wrote, and
it is reported whether or not the first verdict passes. J-house carries no
verdict; its numbers are drawn beside J-rubric's.

**Correction before data (2026-10-30, still before any Jev call).** The
collect step found that 11 of the 59 rulings have no Opus grade before them:
their second bounce came from the free layer, so the draft the owner saw was
never graded by Opus and has no verdict to compare. The owner's ruler is
therefore 48 rulings (16 accept as is, 32 say what is wrong or drop) on 46
drafts, two drafts carrying two agreeing rulings. Opus blocked all 48, so its
accuracy on this ruler is 32/48 = 0.667, and B3 reads: accuracy above 0.667
with the bootstrap interval clear of 0.667. Nothing else moves.

**What a pass or a loss means.** A pass on the first verdict registers a
change to `ytk/curator.py`: the bouncer runs after the lint and before the
Opus call, blocks at θ, and the writer receives the section name and the
rubric section's own text as the finding. Whether a section-name finding gets
fixed in one round is a live question this offline section cannot answer; it
would be measured on the next batch of items, registered first. A loss on
the first verdict closes the bouncer shape for the grader; the Opus call
stays as it is. Cost estimate: 118 requests, roughly 1.5 million input
tokens, under ten cents at the rates the ledger has recorded.

## Result (run 2026-10-30, `pairs.json`, `jev-arms.json`, `scores.json`)

**Both verdicts are registered losses.** *Worth wiring* fails on B1; B2, B4
and stability pass. *Sides with the owner* fails on B3: Jev's accuracy on
the owner's rulings is at the rate null.

| | J-rubric (verdict) | J-house (no verdict) | bar |
|---|---|---|---|
| B1 false blocks on the 13 Opus passes | **6** | 3 | ≤ 1 |
| B2 Opus bounces caught, of 85 | 72 (named section agrees 49/72 = 0.68) | 55 | ≥ 28, named ≥ 2/3 |
| B3 accuracy on the owner's 48 rulings | 0.604 [0.458, 0.750] | 0.542 [0.396, 0.667] | > 0.667, interval clear |
| B4 median wall per draft, 24 questions | 0.26 s (p95 0.40, max 0.51) | same request | ≤ 2.0 s |
| stability, 20 re-sent | decision 20/20, named section 17/18 | | ≥ 18, ≥ 16 |
| rate null (1,000 shuffles of the same blocks) | false blocks 8–12, caught 66–70, owner 0.50–0.69 | | |

Spend: 118 requests, 1,422,111 input tokens, 25 seconds wall for all 98
drafts. 24 states were cut to the 80k cap (the rubric and house rules take
12k of it); the cut group's numbers do not differ from the rest.

**Reading.** The bouncer is too strict to stand at this door. At the
registered 0.8 it turns away 78 of 98 drafts: 72 of the 85 Opus bounced,
which is more than the null's 66–70 and so a real signal, but also 6 of the
13 Opus passed, which is fewer than the null's 8–12 and still six wasted
writer rounds out of thirteen good drafts. Jev's section probabilities sit
high on nearly every draft (`02-the-bouncer-at-the-door.png`, right panel:
the median probability that a draft fails Grounding is 0.73 even on drafts
Opus did not bounce there). Read as a ranker rather than a switch, the
sections do order drafts the way Opus does, modestly: rank AUC 0.70–0.84 on
nine sections, Tags 0.95, What I enjoy reading 0.38 on two cases. A rubric
section is a paragraph of taste, and Jev reads each one as a bar nearly
every draft fails. The curve (`03-threshold-and-the-bill.png`, left) has no
operating point that clears B1 and B2 together: the first threshold with at
most one false block is 0.95, and there the bouncer catches 17 of 85.

On the owner's ruler the bouncer is at chance (0.604 against a null of
0.50–0.69) and below Opus (0.667), because it blocks 15 of the 16 drafts the
owner accepted as they were. The owner's "accept as is" is a judgment about
whether the remaining defects are worth another round; neither Opus nor Jev
is asked that question, and the owner's 24 overrules stand as the only
measurement of it.

The replayed bill (`03`, right) shows what a bouncer with these numbers
would have bought: 72 minutes of the record's 187, every one of them an Opus
grade that ended in a bounce anyway. That is the performance claim, and it
is real; the safety bar is what it costs, and six good drafts sent back for
nothing is above the registered price.

**Post hoc, not registered.** Tags alone (rank AUC 0.95, 18 Opus bounces)
would be the one section a bouncer could stand on; a tags-only check at a
threshold fitted here is a different registration on a different universe,
and the deterministic layer already holds a tag-vocabulary check. The
house-rule arm is safer (3 false blocks) and catches less (55); it clears no
bar either.

**Decision.** The grader's door stays as it is: lint, deterministic checks,
then Opus. The bouncer shape for Jev closes on this record. Across sections
53–57 the pattern is consistent: Jev orders well (AUC 0.92 on connect, 0.70–
0.95 per section here, hit@5 at the local model's number) and decides
poorly at any fixed threshold against a ruler written in the owner's words.
What Jev is for in ytk, if anything, is a ranking score inside a stronger
reader's decision, and no slot in ytk today consumes a score that way. The
program's remaining #219 items are the held-out connect threshold and the
connect state with project context; nothing from this section is added.
