# Path-dependence report: grow-only cache vs fresh derivation

2026-07-13, overnight run. Design: `path-dependence-design.md`, amended per the
Codex review (`path-dependence-design-review-codex.md`) — all seven required
changes (P1-P7) are implemented in `scripts/grove_lab/replay.py`. Data:
144 cells in `replay-cells/*.json` (total grid wall time 1108.5 s). Figures:
`path-divergence-ari.png`, `path-divergence-triplet.png`,
`path-policy-frontier.png`.

## 1. Question and method

**Question.** The shipped grove cache is grow-only: derive the node tree once,
then attach each new note to its nearest node centroid (mass propagates up;
structure never changes). How fast does that incremental state diverge from
what a fresh derivation on the same notes would say, and which rebuild policy
should ship?

**Method.** For each bucket (epicmap n=2065, ai-building n=427, visual-craft
n=86), replay arrival: fit the production tree (`fit_nodes`, average-linkage
cosine, native 384-dim space) on a base prefix, then attach the remainder
one note at a time through the production attach path. Arms:

- Orders: one DATE-ORDERED arm (ties randomized within equal dates, undated
  notes interleaved uniformly at seeded positions — per review P3 this is a
  stress case, NOT a claim of production arrival; no ingest log exists) plus
  5 seeded random permutations (seeds 101-105).
- Base fractions: 0.25 / 0.5 / 0.75 on the date arm; random arms at 0.5.
- Policies: `never` (shipped behavior), `centroid-maintain` (no topology
  change, node centroids updated online from running sums — review P6's cheap
  comparator), and anchored rebuild at debt thresholds theta in
  {0.10, 0.25, 0.50, 1.00}, where debt = attached_since_rebuild /
  n_at_last_rebuild, firing on >= theta (review P1 semantics).
- References at checkpoints 60/70/80/90/100% and immediately pre/post every
  rebuild event: a production-fresh `fit_nodes` reference (shipping frontier)
  AND a matched-k-main reference with k_main frozen to the base tree
  (attribution arm, review P2; renamed post-review — it freezes k_main
  only, NOT sub-split eligibility, so it is a partial capacity control). Inputs frozen and hashed (`vec_sha256` in
  every cell, embedding model `thenlper/gte-small`).
- Metrics: assignment ARI; LCA-triplet agreement with attempted/usable/tie
  accounting (review P5); mass placement via descendant-set node matching
  with mass-share L1, coverage, and Spearman (review P4). Per cell: `auc` =
  mean production ARI/triplet over the fixed checkpoints present in the
  cell — five (60-100%) at base 0.25 and 0.5, but only three (80/90/100%)
  in the 18 base-0.75 cells, where the 60/70% checkpoints cannot exist;
  checkpoints whose triplet agreement is unscoreable (agreement=null) are
  dropped from the triplet mean. `worst_pre_rebuild` = minimum event-level
  pre-rebuild ARI, and cost as wall seconds plus sum of n_rebuild^2
  (review P7).

## 2. Headline findings

Final-checkpoint (100%) divergence, date order, base 0.5, production
reference (matched-k-main in parentheses where it differs):

| bucket | policy | ARI | triplet | mass L1 | ARI-AUC | worst pre | rebuilds |
|---|---|---|---|---|---|---|---|
| epicmap | never | 0.085 | 0.801 | 0.685 | 0.403 | — | 0 |
| epicmap | centroid-maintain | 0.081 | 0.861 | 0.689 | 0.396 | — | 0 |
| epicmap | theta=1.0 | 0.597 | 0.978 | 0.077 | 0.506 | 0.175 | 1 |
| epicmap | theta=0.5 | 0.076 | 0.723 | 0.621 | 0.559 | 0.454 | 1 |
| epicmap | theta=0.25 | 0.762 | 0.977 | 0.054 | 0.727 | 0.097 | 3 |
| epicmap | theta=0.1 | 0.758 | 0.977 | 0.055 | 0.513 | 0.277 | 7 |
| ai-building | never | 0.625 (0.290) | 0.854 (0.941) | 0.333 (0.780) | 0.736 | — | 0 |
| ai-building | centroid-maintain | 0.453 (0.209) | 0.863 (0.962) | 0.422 (0.857) | 0.539 | — | 0 |
| ai-building | theta=1.0 | 1.000 (0.471) | 1.000 | 0.000 (0.494) | 0.811 | 0.624 | 1 |
| ai-building | theta=0.25 | 0.920 (0.405) | 0.977 | 0.159 (0.738) | 0.904 | 0.770 | 3 |
| ai-building | theta=0.1 | 0.973 (0.450) | 0.998 | 0.049 (0.539) | 0.950 | 0.845 | 7 |
| visual-craft | never | 0.317 | 0.732 | 0.337 | 0.339 | — | 0 |
| visual-craft | centroid-maintain | 0.127 | 0.532 | 0.488 | 0.206 | — | 0 |
| visual-craft | theta=0.25 | 1.000 | 1.000 | 0.000 | 0.757 | 0.276 | 3 |
| visual-craft | theta=0.1 | 0.900 | 0.947 | 0.070 | 0.700 | 0.280 | 6 |

(Full grid including theta=0.5 rows and random arms: `replay-cells/*.json`;
aggregation is a mean over the five checkpoint fractions for AUC, min over
rebuild events for worst-pre.)

What the table says:

- **Never-rebuild drifts badly on flat assignment and renderer-visible
  mass.** epicmap never ends at ARI 0.085 with mass-share L1 0.685 — a
  large renderer-visible discrepancy in how girth is distributed. (The L1
  sums |mass-share| gaps over Jaccard-matched nodes at all depths;
  descendant masses nest and unmatched nodes contribute nothing, so the
  value is not a fraction of total girth.) visual-craft never: ARI 0.317,
  L1 0.337.
- **Capacity starvation is a measured drift mechanism in ai-building AND
  visual-craft** (corrected per review K3). Attach never creates nodes:
  ai-building's incremental tree stays at its base 7 nodes while the fresh
  reference grows 7 -> 13 (k_main 3 -> 5 across the n//80 thresholds);
  visual-craft's stays at 4 while references grow to 6 via SUB-SPLIT
  eligibility (its k_main never moves — the "matched-capacity" arm froze
  only k_main, not sub-splitting, so it is renamed matched-k-main and is
  not a full capacity control). The clean negative stands: in the worst
  drifter, `epicmap-date-0.5-rebuild-never.json` (final ARI 0.085, mass L1
  0.685), ref and incremental node counts are identical (15) and k_main
  stays 9 at every checkpoint — epicmap's drift is not attributable to
  measured node-count growth.
- **Capacity growth vs true path dependence: both are real, and their split
  is order-dependent.** ai-building is the only bucket that crosses k
  thresholds inside the replay window at base 0.5. On the date arm the
  matched-capacity reference agrees LESS than production (ARI 0.290 vs
  0.625) — even a same-capacity fresh fit carves the full corpus
  differently, i.e. genuine path dependence in where the base split fell.
  On random arms the direction flips (mc 0.682 vs prod 0.404) — there most
  of the production-reference gap IS the capacity increment. The honest
  statement: neither reference makes never-rebuild look acceptable on
  assignment or mass.
- **centroid-maintain: not recommended, on corrected grounds.** The
  overnight comparator had an initialization bug (review K2: internal
  nodes seeded with a global-mean pseudo-observation instead of their
  descendant mass — `_stamp_centroids` now accumulates descendant sums
  bottom-up, tested). All 24 cm cells were RERUN with the fix. Corrected
  result: cm is worse than plain never on 14/24 arms for final ARI and
  11/24 for final triplet — a wash against doing nothing, not a
  catastrophe — and theta=0.25 beats it decisively on every inspected arm
  (epicmap date ARI 0.074 vs 0.762; visual-craft date 0.150 vs 1.000).
  The earlier claim "dominated in every cell" is RETRACTED (pre-fix it was
  also numerically false: ai-building seed 102 cm 0.586 vs theta 0.580
  assignment AUC). Terminal-only attachment remains untested (review K2's
  second suggestion) — a fresh fit assigns notes only to terminal nodes
  while production attach considers all nodes; that arm is future work.
- **theta=1.0's perfect finals are a trigger-position artifact, not
  quality.** With base 0.5 the doubling trigger fires at the very end
  (epicmap event at n=2064 of 2065; post-rebuild ARI is 1.0 by construction
  since the anchored rebuild IS a fresh fit). Its checkpoint AUC is mediocre
  (epicmap 0.506) and its worst pre-rebuild dip is deep (0.175). Same trap
  for theta=0.5 in reverse: epicmap fires once at n=1548 then attaches 517
  notes stale, ending at ARI 0.076 — exactly the review-P1 warning that
  final-only scoring misleads; AUC and worst-pre are the decision metrics.
- **theta=0.25 is the operationally preferred provisional tradeoff — not a
  data-identified optimum** (reworded per review K1). Counting best-or-tied
  arms across the grid, theta=0.1 actually leads (triplet AUC 13 vs 12
  arms; assignment AUC 14 vs 9); theta=0.25 is preferred only once 3
  rebuilds per doubling is priced cheaper than 7 — a continuity/churn
  judgment (tree renumbering risk, growth-animation noise), asserted, not
  measured. Both are strong: theta=0.25 date-arm triplet AUC 0.913 / 0.969
  / 0.953; theta=0.1 buys ai-building 0.983 and a shallower date-arm
  epicmap worst dip (0.277 vs 0.097) — a transient advantage that is
  date-arm only (deeper than theta=0.25 on 3 of 5 epicmap random seeds).
  The AUC itself is an unweighted checkpoint mean (nulls dropped), not the
  time-weighted integral the design asked for, so the ranking carries
  checkpoint-phase sensitivity (section 6). The single worst transient in
  the whole grid is epicmap seed-102 theta=1.0, worst-pre 0.058. See
  `path-policy-frontier.png`.
- **Caveat on epicmap ARI-AUC ordering** (theta=0.1 at 0.513 below
  theta=0.25 at 0.727): epicmap's fresh references are themselves unstable
  between adjacent prefixes — checkpoints landing mid-cycle catch a moving
  target (its own flat-partition cross-half ARI is ~0.14,
  `shootout-v3.json` `epicmap|agglo-cos|centroid`). For epicmap, flat ARI
  is bounded by reference noise, not policy; rank policies there on triplet
  AUC and mass L1.

## 3. Hierarchy degrades less than assignment and mass at mature bases

(Reframed per review K4: the cross-half floors from `shootout-v3.json` use
full-linkage cophenetic triplets across DISJOINT halves with 1-NN leaf
mapping; the replay uses truncated fit_nodes LCA triplets over the SAME
prefix notes. Numeric equality across these different contracts is
qualitative context, not statistical indistinguishability — no
replay-specific null distribution has been generated. Floors below are
reference points, not verdicts.)

| bucket | reference floor | never, date | never, random mean |
|---|---|---|---|
| epicmap | 0.596 | 0.801 | 0.694 |
| ai-building | 0.752 | 0.854 (mk 0.941) | 0.815 (mk 0.890) |
| visual-craft | 0.738 | 0.732 | 0.929 |

**At base 0.5, ordinal hierarchy agreement stays high (0.69-0.93) while
assignment and mass drift badly** — the raw contrast that matters, stated
without the floor verdict. At base 0.25 the never-rebuild date arm reads
substantially lower in all three buckets (epicmap 0.493, ai-building
0.680, visual-craft 0.701) and mid-run checkpoints dip lower in several
more cells (e.g. epicmap date-0.5 min 0.583). For mature trees,
path dependence lives almost entirely in flat assignment and mass
placement, i.e. in which node a note is filed under and how girth is
distributed — renderer-visible, but not the tree's deep shape. This is why
the shipping decision below is driven by mass L1 and assignment AUC rather
than by any hierarchy emergency; but a young tree (small effective base)
is exactly the shipped starting condition, so the base-0.25 hierarchy
divergence is a real caveat, not a corner case.

## 4. Order and base-fraction sensitivity

**Date vs random (never, base 0.5, final production ARI).** Direction is
bucket-specific; temporal arrival is not uniformly adversarial:

- epicmap: date 0.085 vs random 0.130 [0.062, 0.211] — inside the seed
  envelope.
- ai-building: date 0.625 vs random 0.404 [0.392, 0.418] — date is
  BETTER than every random seed. The known late mixture shift toward
  consumed content (`shootout-v3.json` `ai_building_composition`) is real;
  one hypothesis is that temporally contiguous content arrives in coherent
  runs that attach cleanly, but no run-coherence or attach-quality-by-run
  metric was measured, so the mechanism is unconfirmed.
- visual-craft: date 0.317 vs random 0.637 [0.539, 0.726] — date is worse
  than every random seed; for this bucket temporal order IS adversarial.

**Base fraction (date arm, 0.25 / 0.5 / 0.75).** Never-rebuild degrades as
the base shrinks (epicmap final ARI 0.033 / 0.085 / 0.076; ai-building
0.265 / 0.625 / 0.853; visual-craft 0.251 / 0.317 / 0.465) — the younger
the tree at last derivation, the worse the path dependence, confirming
review P6's premise. Debt-relative theta triggers scale as intended:
theta=0.25 stays in 0.47-1.00 final ARI across all bases and buckets while
its rebuild count adapts (6 / 3 / 1 on epicmap). Finals are not the whole
story, though: the transient dimension also degrades with a young base.
At base 0.25 theta=0.25's worst-pre falls to 0.199 on ai-building (vs
0.770 at base 0.5 — a roughly 4x deeper dip on the bucket whose flat ARI
is not reference-noise-bound) and 0.204 on epicmap, and even the theta=0.1
escape hatch only reaches 0.335 on ai-building (vs 0.845 at base 0.5).
Since a young tree is the shipped starting condition, these base-0.25
transients are decision-relevant. Note the built-in censoring: at base
0.75 no theta >= 0.5 can ever fire (debt cannot reach 0.5 before the
corpus ends), so those cells collapse to never — read the 0.75 column
accordingly.

## 5. Cost

Date arm, base 0.5. `wall_s` is the whole replay cell (attaches + both
references at every checkpoint), so it is an upper bound on production cost;
`work_n2` = sum of n^2 over rebuilds is the deterministic proxy (review P7).

| bucket | policy | rebuilds | wall s | work_n2 |
|---|---|---|---|---|
| epicmap | never | 0 | 15.5 | 1.07e6 |
| epicmap | theta=1.0 | 1 | 20.8 | 5.33e6 |
| epicmap | theta=0.25 | 3 | 25.1 | 9.40e6 |
| epicmap | theta=0.1 | 7 | 35.3 | 1.83e7 |
| ai-building | never | 0 | 1.7 | 4.54e4 |
| ai-building | theta=0.25 | 3 | 2.4 | 4.03e5 |
| ai-building | theta=0.1 | 7 | 2.6 | 7.89e5 |
| visual-craft | never | 0 | 0.9 | 1.85e3 |
| visual-craft | theta=0.25 | 3 | 1.0 | 1.66e4 |
| visual-craft | theta=0.1 | 6 | 1.0 | 2.63e4 |

Even the most expensive cell (epicmap, theta=0.1, 7 anchored rebuilds of up
to 2k notes) is 35 s including all measurement overhead. Rebuild cost is not
a constraint at current corpus sizes; churn (renumbering risk, animation
noise) is the real price of small theta, and anchoring already contains it.

## 6. Limitations

- **The date arm is not production arrival.** No ingest log exists; dates
  are upload/content dates (`e2-report.md` section 1 caveat), coverage
  epicmap 2044/21 dated/undated, ai-building 385/42, visual-craft 80/6,
  ties randomized, undated interleaved at seeded positions. It is a
  stress case with n=1 path per bucket per base fraction.
- **AUC is a 5-checkpoint mean, not a time-weighted integral.** Event-level
  pre/post-rebuild observations exist in every cell and `worst_pre_rebuild`
  covers the transient floor, but the AUC can still land luckily relative
  to rebuild positions (visible in the epicmap theta=0.1 vs 0.25 ordering).
- **epicmap flat-ARI numbers are reference-noise-bound** (intrinsic
  cross-half ARI ~0.14): they measure agreement with an unstable estimator.
  Triplet and mass metrics carry the epicmap decision weight.
- **Matched-capacity attribution is order-dependent** (section 2); the
  frozen-k reference is itself a different estimator at large n, not a
  ground truth.
- **visual-craft cells are small** (86 notes; final checkpoints add ~9
  notes each): single-note reassignments move ARI a lot; its triplet
  usable counts span 260-1499 of 3000 (base-0.25 cells drop to 260-350)
  and the flat metrics are noisy, as pre-registered in the design.
- **epicmap triplet coverage is the worst in the grid, and the epicmap
  decision is delegated to triplet AUC.** Over 200 epicmap checkpoint
  observations fall to 105-400 usable of 3000 attempted (ties up to
  2895), including the headline date-0.5 arm (never-rebuild final
  checkpoint: 351 usable). Additionally, 28 checkpoint observations
  across the grid have agreement=null (unscoreable) and are silently
  dropped from the `auc.triplet` mean — e.g.
  `epicmap-102-0.5-rebuild-never.json`'s AUC 0.712 is the mean of only
  4 non-null checkpoints (its 90% checkpoint has usable=151,
  agreement=null). Rankings that lean on epicmap triplet AUC inherit
  both the coverage collapse and the null-dropping convention.
- **No legibility measurement.** All metrics are structural proxies; E7
  validated full-tree legibility, not a drift threshold. Whether a user
  would notice mass L1 = 0.3 in a rendered tree is unmeasured.
- Post-rebuild agreement is 1.0 by construction (the anchored rebuild is
  the reference fit), so policies are separated only by their between-
  rebuild behavior — which is what AUC and worst-pre report.
- **mass_l1 is a MATCHED-mass L1 — a lower bound.** Unmatched nodes
  (epicmap never headline: 6 per side at coverage 0.902) contribute
  nothing, and the 0.3 Jaccard matching cutoff is unswept (review K5).
  Read every mass_l1 with its adjacent coverage; the headline drift
  conclusion only strengthens under any unmatched-mass penalty.

## 7. Post-review corrections (Codex v5, `external-review-response-codex-v5.md`)

Verdict was results-valid-with-corrections; all seven findings applied:

- K1: theta=0.25 reworded from "frontier knee" to operationally preferred
  provisional tradeoff; theta=0.1's best-tied-arm lead stated; churn cost
  named as judgment (section 2).
- K2: centroid-maintain comparator initialization bug fixed
  (descendant-based, tested), all 24 cm cells rerun; "dominated in every
  cell" retracted; corrected verdict in section 2.
- K3: visual-craft sub-split capacity starvation acknowledged;
  "matched-capacity" renamed matched-k-main (mk) throughout.
- K4: floor verdicts replaced with raw values; cross-construct comparison
  labeled qualitative (section 3).
- K5: mass_l1 relabeled matched-mass lower bound (section 6).
- K6: the 15-note absolute debt floor was MEASURED post-review: 24 hybrid
  cells (`*-rebuild-0.25f15.json`). At base 0.5 it is identical to pure
  theta=0.25 in 12/18 arms; the difference concentrates where designed —
  visual-craft trades one rebuild for final ARI 1.000 -> 0.887 and
  triplet 1.000 -> 0.960. Known, bounded.
- K7: `gate72.json` regenerated decision-grade: 10 triplet-sampling seeds
  on fixed temporal halves with tie/collision accounting, and BOTH
  constructs explicitly named — full_linkage_triplet (0.476 / 0.612 /
  0.664) and fit_nodes_triplet, the truncated topology snapshots actually
  render (0.622 / 0.742 / 0.947), structure nulls ~0.33. Note the epicmap
  fit_nodes gate carries heavy tie-rejection (usable ~18k of 40k), a
  shallow-tree property to keep beside the number.
