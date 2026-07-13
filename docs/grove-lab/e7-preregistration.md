# E7 preregistration: grove readback (single-subject case study)

Status: FROZEN pending implementation. Incorporates every Codex v2
protocol edit (`external-review-response-codex-v2.md`: G1, G4, G6,
`e7_protocol_edits`). The subject (the vault's owner) is naive and can be
exposed exactly once; no rendered true-vs-control comparisons may be shown
to him before the run. This document contains no images.

## Framing (G6)

This is a descriptive single-owner case study, not a population inference.
There is no single p < .05 "legibility gate." Repeated views of three
buckets are not independent replications. Exact binomial tail
probabilities may be reported as conditional summaries only.

## Constructs (G1) — two tasks, never conflated

- **Task 1 — semantic readback (the product question).** One bucket NAME
  is shown, plus two structurally matched trees side by side: the bucket's
  true tree and a constrained-shuffle control of the SAME bucket.
  Left/right randomized. Question: "which is your <name> tree?"
  This tests whether data-derived organization carries readable topic
  identity.
- **Task 2 — topology invariance (the rendering question).** An anchor
  tree, plus two candidates: the anchor's topology re-rendered with a
  different visual seed, and its constrained shuffle. Question: "which
  candidate shares the anchor's structure?" This tests whether the
  renderer preserves perceptible topology. It is NOT topic discrimination
  and does not gate legibility.
- 3-AFC isolated-tree identification (see a tree, name the topic) is run
  last and reported as exploratory only.

## Stimuli (G4)

- Buckets: epicmap, ai-building, visual-craft (saplings excluded — no
  topology to test).
- Controls are generated automatically by degree-preserving subtree
  reattachment/edge swaps that preserve: node count, root degree, depth
  histogram, child-count sequence, and mass/persistence strata by depth —
  while breaking which subtrees are adjacent. Candidate controls are
  accepted only within preregistered tolerances (each preserved statistic
  within 10% or exactly equal where discrete); generation is seeded and
  hashed; NO hand-selection of visually convincing shuffles.
- Rendering: neutral tint for all stimuli (no per-topic hue), identical
  knob preset, identical leaf density. Presentation scale NORMALIZED
  across trees in Tasks 1-2 (sqrt(n) scale disabled) so size cannot answer
  the question. An optional post-run product block with hue and scale
  restored may be run AFTER the primary tasks and is reported separately.

## Randomization

- Complete manifest pre-generated and content-hashed before the first
  trial: stimulus hashes, control-generation constraints and seeds,
  presentation order, left/right truth, camera azimuth seeds, analysis
  version.
- Order randomized; bucket and condition balanced across early and late
  trials; left/right randomized per trial; no feedback of any kind during
  the run.
- Practice: 2 warm-up trials using synthetic trees (generated BFS, not
  from any bucket) to teach the interface; excluded from analysis.

## Trials and scoring (preregistered)

- Task 1: 9 trials (3 per bucket, distinct control seeds).
- Task 2: 9 trials (3 per bucket).
- Exploratory 3-AFC: 6 trials (2 per bucket).
- Collected per trial: choice, confidence (1-5), response time.
- Exclusions: none post hoc; interface malfunctions are logged and the
  trial marked void in the raw log, never deleted.
- Outcome definitions, committed now:
  - Task 1 per-bucket: 3/3 = clear read; 2/3 = weak; <=1/3 = no read.
  - Task 1 overall: >=7/9 = topology carries topic identity; 5-6/9 =
    inconclusive; <=4/9 = it does not (for this subject, this render).
  - Task 2 uses the same bands, gating only the RENDERING claim.
  - Early-vs-late split reported for learning effects.
- Analysis reports point scores, per-bucket breakdown, confidence, RT,
  and (conditional summary only) exact binomial tails at p0 = 1/2.

## Implementation contract

- `/grove?readback=1` consumes an immutable versioned manifest
  (`~/.ytk/grove/e7-manifest.json`); responses append to
  `docs/grove-lab/e7-responses.json` (raw log, never overwritten,
  correctness never displayed).
- The manifest generator lives in `scripts/grove_lab/e7_manifest.py` and
  refuses to regenerate over an existing manifest without `--force`,
  which also voids the naive-subject status in the log.

## Amendments (pre-exposure, before any scored stimulus was viewed)

1. **Camera azimuth randomization is realized by per-stimulus render
   seeds.** Fork azimuths in the generator are isotropic, so an
   independent render seed is equivalent to rotating the camera; no scene
   change needed. Recorded in the manifest's render note.
2. **Second constrained-control move: payload permutation within depth.**
   Within-level parent permutation is identity-locked on topologies where
   a level's children all share one parent (true of visual-craft:
   root -> 3 limbs -> 2 sub-branches under one limb). The control
   therefore also permutes (mass, persistence) payloads within each depth
   level — wire topology unchanged, every preregistered stratum preserved
   exactly, joint mass-by-position signature (the semantic content)
   broken. Implemented in `e7_manifest.shuffle_topology`, tested.
3. **Response log location:** `~/.ytk/grove/e7-responses.jsonl` (the hub
   cannot write into the repo); archived to `docs/grove-lab/` after the
   run completes.

## Amendments after Codex v3 audit (still pre-exposure; blocking findings fixed)

4. **Amendment 1 RETRACTED (Codex H5 rejection accepted).** A render seed
   changes geometry, not the camera. Now separated: every stimulus carries
   an explicit `camera_azimuth`; task-1 pairs share BOTH geometry seed and
   azimuth (only structure differs); task-2 stimuli carry independent
   geometry seeds (render invariance is the construct) with recorded
   azimuths. Scene rotates the camera from the payload azimuth.
5. **Truth isolation (H1):** public manifest carries opaque stimulus ids
   (s00..sNN) and no role or answer information anywhere (tested by
   serialization grep); answers + id map live in a private
   `e7-answer-key.json` the trial pipeline never reads.
6. **Block structure (H2/H6/H7):** practice, then each bucket's FIRST
   task-1 exposure (randomized bucket order, marked `primary` — the only
   uncontaminated semantic observations), then task-1 repeats (secondary,
   learning-sensitive), then task 2, then exploratory identification
   strictly last. Left/right balanced within task groups. All ordering
   properties are unit-tested, not promised.
7. **Response integrity (H3/H4):** server validates trial ids, per-trial
   allowed choices, confidence 1-5, non-negative RT; idempotent by
   manifest hash + trial (exact duplicate acknowledged, conflicting
   duplicate rejected 409); GET returns completed trials for
   server-backed resume. UI locks controls during submission, advances
   only on confirmed persistence, offers retry on failure, and reveals
   choices — and starts RT — only after every canvas reports planted and
   the growth animation has finished.
8. **visual-craft construct (H8):** each task-1 trial is marked
   `adjacency` or `payload` by whether its control moved parent links.
   Payload-construct trials are preregistered as payload-geometry
   readback and reported separately from adjacency-construct trials;
   they do not pool into the semantic-legibility claim.
9. Manifest regenerated (seed 72) after these fixes; the prior manifest
   was never run past practice, so naive-subject status is intact.

## Contamination rule

Until the run completes: no rendered true-vs-control image may appear in
chat, reports, commits, or the hub for the three test buckets. Violation
= the affected bucket's trials are demoted to exploratory.
