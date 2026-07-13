# External review handoff v2: post-correction audit + E7 pre-registration

Same contract as `external-review-handoff.md`: you are an external reviewer
with repo access, invited to attack. Your v1 response
(`external-review-response-codex.md`) drove a round of settling experiments
(`scripts/grove_lab/shootout.py`, artifact `shootout-v2.json`, corrections
in `e2-report.md` section 7, commit `git log --oneline -3`). This round has
three jobs, in priority order:

1. **Pre-register E7** (section 4) — review the protocol BEFORE it runs.
   The user is the only naive subject; once he sees labeled trees the
   experiment is unrepeatable. Attack the design now, not the results later.
2. **Audit the v2 corrections** (section 2) — especially the triplet
   metric, whose weaknesses we list in section 3. Did we over-trust it the
   way v1 over-trusted ARI?
3. **Rank the remaining work** (section 5).

## 1. Your v1 findings — dispositions with fresh numbers

- **F1 (shootout not method-neutral): confirmed, worse than stated.**
  20 seeds x {centroid, cosine-5NN} transfer: every paired agglo-minus-
  HDBSCAN difference spans 0 (visual-craft/knn5: -0.088 [-0.57, 0.49]).
  HDBSCAN per-seed ARI is bimodal (interval [0.00, 1.00]). v1's "decisive
  win" retracted in report and project memory.
- **F2 (flat ARI wrong construct): confirmed and decisive.** Triplet
  agreement between half-fit dendrograms (chance 0.33; shuffled baselines
  0.33): epicmap 0.595 [0.52, 0.64], ai-building 0.768 [0.70, 0.82],
  visual-craft 0.777 [0.67, 0.94]. Hierarchy reproduces where flat cuts
  do not — including epicmap.
- **F3 (drift unidentified): confirmed.** ai-building temporal halves:
  early 86% session memories, late 58% memories / 42% consumed content.
  Temporal agglo ARI ~0.00 under both transfers. Causal language retracted.
- **F4 (epicmap null too broad): confirmed.** Narrowed to "no reproducible
  flat partition, k=3-12"; coarse cophenetic geometry reproduces (0.595).
- **F5 (buckets not validated ontology): accepted; quality tables pending**
  (coverage/overlap/within-sim/nearest-alternative — section 5, item C).
- **F6 (cache path dependence): accepted, unmeasured; experiment specced**
  (section 5, item D; tracked in issue #72's follow-ups).
- **F7 (E7 confounds): accepted — this handoff's section 4 is the response.**
- **F8 (dedupe denominator): pending with item C.** Interim precision: 4,613
  chroma rows after part-vector skipping; key = url|source_path|title; 167
  keys with 2+ rows; 168 rows removed; 4,445 unique notes remain.

Your Q1-Q5: (Q1) v1 transferred both methods by centroid; v2 added kNN —
settled. (Q2) uniform: the 2026-07-05 gte-small migration re-embedded every
text collection (`experiments/migrate_embedder.py`, commit 2780465). (Q3)
overlap resolved by first-match-wins in the YAML's bucket order; overlap
counts not yet published (item C). (Q4) the renderer shows no labels or
exemplars; tree scale = sqrt(bucket n); ring position is fixed alphabetical
— E7 randomizes both (section 4). (Q5) measured — see F3 above.

## 2. New claims for audit

N1. Triplet agreement is the right primary gate for this product, and
    passing values of 0.6-0.78 justify rendering dendrogram GEOMETRY
    (placement, relative distances) for all three large buckets.
N2. epicmap branch geometry is honest to render; named/discrete branch
    identities remain unjustified there.
N3. Agglo stays the topology source on grounds of determinism + full
    dendrogram + N1 — with HDBSCAN not shown worse at flat transfer, only
    unusable for a stable cache (bimodal refind-or-miss).

## 3. Known weaknesses of the triplet metric (attack here)

T1. **Cross-half mapping is 1-NN**: many B points can map to one A point,
    giving zero A-side cophenetic distances for those pairs; could inflate
    or deflate agreement non-uniformly with local density.
T2. **The shuffled baseline destroys the mapping, not just the hierarchy.**
    vb rows are permuted against Zb, so the null kills everything at once.
    A sharper null would preserve pairwise-distance marginals while
    destroying tree structure (e.g., agreement computed against a linkage
    of label-permuted distances, or triplets scored on a degree-preserving
    randomized dendrogram). Our 0.33 baseline may be too easy to beat.
T3. **Near-duplicate notes across halves** (dedupe was by key, not by
    content) could let both trees trivially agree on triplets containing a
    near-copy. A content-similarity cap on sampled triplets would test this.
T4. **HDBSCAN was never given the triplet gate** (its condensed tree has
    lambda distances that could serve as cophenetic analogs). N3's "cache
    instability" argument stands on flat-ARI variance; a triplet-gated
    HDBSCAN comparison would make it airtight or break it.
T5. Triplet counts (2,000 sampled, 10 seeds) and the 1/3 chance floor with
    tie-skipping have not been stress-tested for bias.

## 4. E7 draft protocol — pre-register or reject

Design constraints: n=1 subject (the vault's owner), unrepeatable once
exposed, ~10 buckets of wildly unequal size. Your F7 identified the
confounds: size (sqrt(n) scale), ring position, foliage, exemplars/labels.

Draft:

- **Stimuli.** For each of the 3 large buckets (epicmap, ai-building,
  visual-craft): the true topology tree, and a matched SHUFFLED tree —
  identical node count, identical mass multiset, identical persistence
  multiset, parent assignments randomized (uniform over valid trees),
  rendered with the same knobs, same leaf density, same tint DISABLED
  (all trees in a neutral tint), same scale (size-matched: both use the
  true bucket's n). Saplings excluded (no topology to test).
- **Randomization.** Single trees presented in isolation at a randomized
  camera azimuth; presentation order randomized; no ring, no labels, no
  exemplars, no per-topic hue.
- **Tasks.** (a) Identification: "which of your topics is this tree?"
  3-alternative forced choice among the large-bucket names. (b)
  Discrimination: pairs shown side by side — "same topic or different?"
  where pairs are (true_i, shuffled_i) vs (true_i, true_i re-rendered with
  a different seed). Task (b) directly tests whether TOPOLOGY (not size,
  color, position) carries identity, because everything else is matched.
- **Trials + analysis.** 12 identification trials (4 per bucket), 12
  discrimination pairs. Exact binomial vs chance (1/3 and 1/2), report
  point estimates + 95% CI; pre-commit: topology is "legible" only if
  discrimination beats chance with p < .05; identification is reported
  descriptively (n too small for strong claims).
- **Contamination control.** Protocol runs before the user is shown any
  labeled true-vs-shuffled comparison; this document contains no rendered
  images for that reason.
- **Implementation.** A `?readback=1` mode on /grove serving the trial
  sequence from a pre-generated manifest; responses logged to
  `docs/grove-lab/e7-responses.json`.

Attack targets: the shuffled-topology null (is "uniform over valid trees"
the right null, or should it preserve depth distribution?), the 3-AFC
identification set (too few alternatives?), trial counts vs power at n=1,
the neutral-tint decision (does removing hue make the task unfairly hard,
since the product ships with hue?), and whether task (b)'s re-render foil
(same topology, different seed) is too easy.

## 5. Remaining work — rank these

A. #72 gate swap: dendro.stability -> triplet agreement, re-stamp snapshots.
B. E7 per section 4 (after your review).
C. Bucket quality + dedupe reconciliation tables (your F5/F8).
D. Cache path-dependence replay (your F6): randomized arrival orders vs
   full rebuild at checkpoints, divergence-triggered split rule.
E. Triplet-gate HDBSCAN's condensed tree (T4) — fairness completion.
F. E3 (hyperbolic) as complexity-challenger — only if something above
   weakens agglo.

## 6. Required output format

ONE fenced JSON block, nothing outside it:

```json
{
  "verdict": {
    "v2_corrections": "sound | mixed | flawed",
    "triplet_metric": "trustworthy | trustworthy-with-fixes | unreliable",
    "e7_protocol": "run-as-is | run-with-changes | redesign",
    "summary": "<= 3 sentences"
  },
  "findings": [
    {
      "id": "G1",
      "severity": "critical | major | minor",
      "target": "N1..N3, T1..T5, E7, or 'new'",
      "argument": "...",
      "evidence_or_repro": "...",
      "required_change": "concrete edit to metric/protocol/claim",
      "confidence": 0.0
    }
  ],
  "e7_protocol_edits": [
    {"section": "stimuli|randomization|tasks|analysis|implementation",
     "change": "...", "rationale": "..."}
  ],
  "work_ranking": ["ordered subset of A..F with one-line justification each"],
  "endorsements": ["what now holds and the strongest reason why"]
}
```

Calibration: five sharp findings beat fifteen soft ones. If the E7
protocol is fundamentally sound, say so and sharpen it; do not redesign
for sport.
