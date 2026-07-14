# 2026-07-13 — Grove science sprint: four method failures, one legibility result

## Summary

Across roughly thirty hours (2026-07-12 evening to 2026-07-14 early
morning) the grove went from a hand-tuned procedural toy to an
evidence-bearing representation: topic trees grown from the vault's own
embedding hierarchy, validated by a preregistered single-subject readback
experiment (E7) that the owner passed 3/3 on its only uncontaminated
trials, and a 192-cell cache-policy study that measured — rather than
argued — how the shipped grow-only cache should be maintained.

The same thirty hours produced four genuine methodological failures, each
caught not by us but by an adversarial review loop (Claude authoring
handoff documents, an external Codex model attacking them, disagreements
settled by new experiments rather than by prose). Two failures produced
confidently wrong conclusions that were later retracted in place; one was
a comparator bug that denied a design alternative a fair trial; one — the
deepest — was a version-skew error in which fixing earlier findings
silently destroyed the comparability of the whole experimental grid. The
net result: every headline number that survives is one that survived an
attack, and the failures are now doctrine (five feedback/method memories,
one architectural rule set). Scope: 29 commits, tests 409 -> 441, ~384
replay cells, seven external review documents, one irreversible human
experiment run exactly once. Technical numbers live in
`docs/grove-lab/e2-report.md`, `e7-results.json`,
`path-dependence-report.md`, and `path-dependence-v3-addendum.md`.

## The arc, compressed

| phase | what happened | artifact |
|---|---|---|
| E1 pre-flight | corpus recon killed most scalar signals (burstiness dead, spread alive, intrinsic dim ungateable); 4 of 9 groups temporally unsplittable | e2-report.md section 3 |
| The bucket correction | the user rejected directory provenance as the topic axis ("no fucking duh its hard to visualize if you blindly take the db as source of truth") — buckets became a user-authored file | ~/.ytk/grove_buckets.yaml, memory: map-groups-by-provenance-not-topic |
| E2 | HDBSCAN condensed tree failed its own stability criterion; average-linkage shipped as topology source; grow-only cache with anchored rebuilds; data-native renderer behind a toggle | dendro.py, datatree.ts, /api/grove |
| Review rounds 1-2 | "agglo wins decisively" RETRACTED (2-seed noise); flat ARI replaced by triplet agreement; epicmap null narrowed | shootout-v3.json, e2-report.md sections 7-8 |
| E7 | four pre-run review rounds hardened an unrepeatable experiment; owner passed: primaries 3/3, identification 6/6 at 3.7s median | e7-preregistration.md, e7-results.json |
| Overnight study | 144-cell path-dependence grid via workflow; theta=0.25 recommended | path-dependence-report.md, morning-decisions.md |
| Reviews v5-v6 | comparator init bug; then the version-skew finding that HELD both ship decisions | external-review-response-codex-v{5,6}.md |
| Replay v3 | 192 cells under one stamped engine: ranking held, persistence staleness measured (large), terminal-only attach quantified (wins 23/24 arms, insufficient alone) | replay-cells-v3/, path-dependence-v3-addendum.md |
| Shipped besides science | ingested_at capture (immutable, first-write-wins); variant UI removed; chroma double-indexing found and ledgered (#71) | store.py, grove.tsx |

## Symptom

No single alert — the triggering pattern repeated four times and is worth
naming so it is recognizable: **a conclusion that felt settled was
presented to an external reviewer, and a specific, checkable counter-claim
came back.** The four instances: "agglo-cosine 0.75/0.88 vs HDBSCAN
0.10/0.34" (Codex F1: your transfer rule assumes centroid compactness and
you ran 2 seeds); "dominated in every cell" (Codex K2: your comparator
initializes internal-node centroids with a global-mean pseudo-observation
— and the dominance claim is numerically false at ai-building seed 102);
"identical to pure theta=0.25 in 12/18 arms" (Codex v6 finding 1:
identical trigger schedules but different AUCs — you are comparing cells
from two different engines); and the E7 protocol's "answer stripped"
endpoint (Codex H1: your stimulus ids literally contain the string
`true`).

## Findings

### Finding 1 — Two-seed comparison presented as a decisive result

`scripts/grove_lab/` (scratch heredoc, superseded by `shootout.py`). The
first method shootout ran 2 random-half seeds per cell and reported means
with no intervals; the "decisive" agglo-vs-HDBSCAN margin was a draw from
distributions whose per-seed ARI later measured as bimodal (HDBSCAN
visual-craft interval [0.00, 1.00]). With 20 seeds and paired
differences, every difference spanned zero. Root cause: a quick scratch
experiment's output was promoted to a shipped conclusion without
promotion-grade statistics. Fix: `shootout.py` (committed, 20 seeds,
paired intervals, both transfer rules); retraction recorded in
`e2-report.md` section 7 and rewritten into the project memory rather
than deleted.

### Finding 2 — Construct mismatch: a flat-partition gate on a tree product

`scripts/grove_lab/dendro.py` stability gate (v1) scored cross-half ARI
of flat cluster labels while the product renders a hierarchy. Codex F2
named it; the repaired gate (sampled triplet agreement over cophenetic /
LCA order, `shootout.py:triplet_agreement`) reversed part of the verdict:
hierarchies reproduce (0.60-0.78 vs a 0.33 structure null) even where
flat partitions do not — including epicmap, whose "no substructure" claim
was accordingly narrowed. Root cause: the most convenient metric, not the
construct-matched one, became the gate. The metric itself then needed its
own repair round (symmetric scoring, injective triplets, tie handling —
Codex G3; structure null — G5) before its numbers stabilized.

### Finding 3 — Comparator bug denied an alternative a fair trial

`scripts/grove_lab/replay.py:_stamp_centroids` (pre-fix): internal nodes
with no direct members were initialized as `_sum=global_mean, _count=1` —
a pseudo-observation — then updated online. The centroid-maintenance
policy was "rejected by measurement" on the strength of cells where its
attach targets were malformed. Fixed with descendant-based bottom-up
accumulation (tested,
`tests/test_grove_replay.py:test_internal_node_centroids_init_from_descendants`),
all 24 cells rerun: corrected cm is a wash against never-rebuild and
still loses to theta=0.25 — same conclusion, honest grounds, retraction
of the dominance language.

### Finding 4 — Version skew: local fixes destroyed global comparability (deepest)

The Finding-3 fix changed `_stamp_centroids` for EVERY policy, but only
cm and new hybrid-floor cells were rerun; they were then compared against
never/theta cells from the older engine. Proof of skew: epicmap date-0.5
pure theta=0.25 vs hybrid — identical trigger schedules (3 rebuilds
each), different AUCs (0.913 vs 0.927). Compounding it, the decision doc
carried hybrid numbers copy-forwarded from pure-theta cells (Codex v6
finding 7, confirmed against artifacts to the digit), and the hybrid
cells simulated centroid semantics production does not have
(`ytk/grove` production keeps direct-member/global-mean centroids,
`dendro.py`). Root cause, in Codex's words, which deserve to be quoted
because they generalize: "review compliance is being treated as
experimental validity." Fix: centroid semantics became a parameter
(`mode="production"|"descendant"`), every cell stamped with
`schema_version` + `engine_commit`, and the full 192-cell grid rerun
under one engine (`e0e903c`) — which also finally measured the two things
the earlier grids could not: persistence (branch-length) staleness, and
the terminal-only attach arm.

### Finding 5 (near-miss) — The E7 protocol would have leaked its answers

Caught pre-run, which matters because E7 was unrepeatable (one naive
subject). The v1 implementation leaked truth through role-bearing
stimulus ids (`epicmap-t1-0-true` served over the network), allowed
topology-invariance trials to teach the true trees before semantic trials
measured them, lost responses on failed POSTs (advance in `finally`), and
started reaction timing before WebGL mounted. Four blocking findings
(Codex H1-H4), all fixed and re-audited to `clear_to_run: true` before
the subject saw a single scored stimulus. The run then produced the
session's headline positive result.

### Non-finding — Embedding-pipeline uniformity

Codex Q2 asked whether the temporal splits were confounded by the July 5
embedder swap (gte-small replacing MiniLM). Verified clean:
`experiments/migrate_embedder.py` (commit 2780465) re-embedded every text
collection; one model, one space. Recorded so nobody re-investigates.

## Why so many things were wrong simultaneously

Every failure is the same failure at a different altitude: **local
validity mistaken for global validity.** A 2-seed mean is locally valid
arithmetic — globally meaningless without variance. Flat ARI is a locally
valid clustering metric — globally mismatched to a hierarchy product. The
cm comparator locally implemented "maintain centroids online" — globally
it never implemented the premise (centroids that start correct). And the
v5 correction pass was locally impeccable — every finding got a fix — while
globally it manufactured an incomparable grid.

They compounded because the loop that produced them optimizes for
momentum: single-author, high-velocity, each artifact building on the
last within hours. That loop has no internal adversary, so errors do not
surface between steps; they surface only when the whole edifice is handed
to someone whose job is to break it. This is also why the failures were
caught in ORDER of depth: the reviewer first attacked the statistics
(cheap to check), then the constructs (requires re-derivation), then the
comparator's semantics (requires reading the implementation against its
premise), and only at v6 the cross-artifact consistency (requires holding
the entire grid in view). Each round's fixes exposed the next layer
precisely because the shallower noise above it was gone.

The version-skew finding was the most hidden because nothing in any
single artifact was wrong: every v5-era cell was internally correct,
stamped only implicitly by mtime, and individually reproducible. The
error existed only in the RELATION between artifacts — which is exactly
the place a single-author loop never looks and a fresh adversary looks
first.

One failure was prevented rather than caught after the fact, and the
difference is instructive: E7 was treated as irreversible from the start
(one naive subject), which forced preregistration, contamination rules,
and pre-run audits. Where we assumed irreversibility, we got the
discipline right; where reruns felt cheap (replay grids), we got sloppy.
Cheap-to-rerun is what made rerunning-partially thinkable.

## Repair

| commit | change |
|---|---|
| 5fd825b..24b7735 | E2 pipeline: buckets, dedupe, linkage topology, cache, hub endpoint, renderer, first report |
| 56a5d14, 27a30bb | variant UI removed; first review handoff |
| shootout v2 commit | 20-seed rerun: agglo-win retraction, triplet gate adopted |
| triplet-v2 commit | metric repaired (symmetric/injective/ties), structure null, HDBSCAN single-linkage gated fairly; E7 preregistered |
| E7 fix commits | opaque ids + answer key, block ordering, idempotent/resumable server, readiness-gated RT |
| e7 results commit | 26 trials logged and scored per prereg |
| overnight commits | replay engine v2 (P1-P7), 144 cells, morning docs |
| v5 correction commit | cm init fix + reruns, hybrid floor cells, gate72 v2 |
| v6 hold commit | ship items HELD, copy-forward numbers corrected, meta-lesson recorded |
| 922ff01-adjacent | ingested_at capture (immutable, first-write-wins) |
| e0e903c | replay engine v3: parameterized centroid semantics, persistence metric, terminal arms, artifact stamping |
| 13548af, 02b217d | 192-cell v3 grid + verified addendum; decision (a) measurement-complete |

Post-fix verified numbers: `path-dependence-v3-addendum.md` (all claims
traceable to `replay-cells-v3/*.json`, engine-stamped).

## What we got right

- **Disagreements were settled by experiments, never by argument.** Every
  review round ended in a new artifact (shootout v2/v3, cm rerun, floor
  cells, gate72 v2, replay v3), not a rebuttal. Several "defenses" would
  have been wrong; the experiments were not.
- **Retractions were recorded in place.** Memories and reports were
  rewritten to carry the correction AND the original error
  (agglo-cosine-beats-hdbscan-native.md is now a retraction that teaches);
  nothing was quietly deleted.
- **Irreversibility discipline on E7.** Preregistration, contamination
  rule (no true-vs-control images anywhere the subject could see),
  truth-free serving, resume-safe logging, and a scoring script that
  refuses partial runs. The one experiment that could not be redone was
  the one run correctly the first time.
- **Kill criteria were stated before results existed** (E1 signal gates,
  E2 stability criterion, E7 outcome bands) — which is why killing
  burstiness, HDBSCAN-native, and the cm policy produced no argument.
- **Production code paths were reused in experiments** (the map's loading
  contract, dendro's fit/attach/anchor) — so findings transfer to the
  shipped system instead of describing a simulation of it. (Finding 4 is
  the exception that proves the rule: the one place experiment semantics
  silently diverged from production is where the deepest error lived.)
- **Everything is re-derivable.** All 384 cells, gate numbers, and
  figures are committed; every disputed number in every review round was
  settled in minutes by recomputation.

## What we'd do differently

- **Promotion-grade statistics from the first comparison.** Any
  method-vs-method claim gets >= 20 seeds and paired intervals before it
  is written down anywhere a decision can read it. (Failure mode:
  Finding 1; memory: agglo-cosine-beats-hdbscan-native.)
- **When shared experiment code changes, the whole comparable grid
  reruns — no exceptions, no "only the affected cells."** (Failure mode:
  Finding 4; memory: review-compliance-is-not-validity.)
- **Numbers in decision documents are recomputed from artifacts at edit
  time, never carried forward through an edit.** (Failure mode: v6
  finding 7.)
- **Match the metric to the rendered construct before gating anything.**
  Ask "what does the user actually see?" first; ARI was measuring a thing
  nobody renders. (Failure mode: Finding 2.)
- **Ask what is in the data before computing on it.** The user's bucket
  correction ("you never cared to ask whats in there") reframed the whole
  project in one message; the E1 recon that followed should have been the
  first act, and the axis question should have been put to him before any
  statistic ran.
- **Set worker models explicitly in fan-outs.** ~48 shell-running agents
  inherited the expensive session model across two workflows for zero
  quality gain. (Memory: feedback-workflow-agent-models.)

## Prevention

- **Architectural rules (now doctrine):** every experiment artifact
  carries `schema_version` + `engine_commit`; one engine version per
  comparable grid; a new metric ships with its own null, not a borrowed
  one; experiment code that simulates production either reuses the
  production path or declares the divergence in the artifact.
- **Tooling:** workflow validate phases check artifact stamps, not just
  existence; unit tests pin exact trigger positions and semantics
  (`test_grove_replay.py`); verification lenses in synthesis workflows
  explicitly hunt copied-forward numbers.
- **Documentation:** seven memories written or corrected this session
  (provenance-vs-topic, cache-grow contract, agglo retraction, epicmap
  correction, review-compliance, workflow models, E7 results) — each
  carries the why and the how-to-apply, and wrong ones were rewritten
  rather than removed.
- **Cultural:** the handoff -> external-review -> settling-experiment
  loop is now the standing practice for any conclusion that gates a
  decision; every round this session either changed a conclusion or
  blocked a flawed irreversible step, at a cost of hours against errors
  that would have shipped. Treat "cheap to rerun" as a warning sign, not
  a comfort: the discipline applied to the unrepeatable experiment is the
  discipline that was missing from the repeatable ones.

## Where this leaves the grove

The premise is validated within stated limits: for this owner, corpus,
and renderer, data-derived hierarchical geometry carries recognizable
topic identity (E7: 3/3 uncontaminated primaries, 6/6 exploratory
identification at 3.7s median; visual-craft's 6-node payload condition
was a no-read; one subject, one render). The cache question is measured:
never-rebuild drifts badly on assignment, girth, and branch length;
theta=0.25 with a 15-note floor plus terminal-only attach is the
recommended containment, gating now on engineering (persistent debt
state, migration, atomic snapshots, descendant-based anchoring — v6
finding 2's honest scope). The gate swap (#72) holds for a fit_nodes
null. Ingest timestamps accrue from 2026-07-13 forward, making a true
production-arrival replay possible in a few months. The decoration track
(cosine palettes, uncertainty-as-atmosphere, freshness glow, dissolve
lifecycle, glow wires) is unblocked as product work and handed to a new
session via `shader-brainstorm-handoff.md`.

The grove earned its glow wires. The lab earned its checklist.
