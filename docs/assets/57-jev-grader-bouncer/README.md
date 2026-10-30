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

**What a pass or a loss means.** A pass on the first verdict registers a
change to `ytk/curator.py`: the bouncer runs after the lint and before the
Opus call, blocks at θ, and the writer receives the section name and the
rubric section's own text as the finding. Whether a section-name finding gets
fixed in one round is a live question this offline section cannot answer; it
would be measured on the next batch of items, registered first. A loss on
the first verdict closes the bouncer shape for the grader; the Opus call
stays as it is. Cost estimate: 118 requests, roughly 1.5 million input
tokens, under ten cents at the rates the ledger has recorded.
