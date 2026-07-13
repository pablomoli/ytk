# Overnight experiment design: grow-only cache path dependence (item D)

For review before execution. E7 established that a tree derived from ALL
of a bucket's notes at once is legible to its owner. The shipped grove is
a grow-only cache: derive once, then attach new notes to their nearest
existing node (mass propagates up; structure never changes; anchored
rebuild only on explicit --rebuild). This experiment measures whether and
how fast incremental attach diverges from what a fresh derivation would
say, and derives a rebuild policy from the measured curves. Decision in
the morning: which trigger ships.

## Protocol

- Buckets: epicmap (2065), ai-building (427), visual-craft (86).
- Arrival orders per bucket: the real TEMPORAL order (primary; this is
  what production actually experiences) + 9 seeded random permutations
  (sensitivity: is temporal arrival specifically adversarial?).
- Replay: derive the node tree (production `fit_nodes`, average-linkage
  cosine, native space) on the first 50% of notes in arrival order; then
  attach the remainder one at a time via the production attach path
  (`attach_new_notes`: nearest node centroid, mass up the ancestor chain).
- Checkpoints at 60/70/80/90/100% of the bucket: compare the incremental
  state against a fresh `fit_nodes` derivation on the SAME prefix. Both
  sides are fit_nodes node-trees, so granularity is matched by
  construction.

## Metrics per checkpoint (all three, none alone)

1. **Assignment agreement** — ARI between the two structures' note->node
   labels over shared notes (chance-corrected "do notes live in the same
   groups").
2. **Hierarchy agreement** — triplet agreement (the E7-era ordinal gate)
   using each node-tree's LCA-depth ultrametric over notes; ties skipped
   on either side, symmetric. Within-node distances are 0 on both sides
   equally.
3. **Mass placement** — after member-overlap node matching
   (`anchor_nodes`), Spearman rank correlation of matched nodes' mass
   shares (does girth still sit where a rebuild would put it?).

## Policy simulation (the decision generator)

Rebuild triggers: re-derive (anchored, production path) whenever notes
attached since the last derivation exceed theta of the tree's size, for
theta in {0.10, 0.25, 0.50, infinity (never = current behavior)}.
Report per (bucket, theta): final divergence at 100% on all three
metrics, number of rebuilds incurred (cost), and the max transient
divergence along the way. The morning menu is the measured frontier:
staleness vs rebuild churn.

## Deliverables by morning

- `docs/grove-lab/path-dependence.json` (versioned cells, embedding model
  stamped), divergence-curve + policy-frontier figures, a morning
  decision doc with the policy menu, plus two riders: bucket quality +
  dedupe reconciliation tables (review item C) and triplet-gate numbers
  for all snapshots (issue #72 groundwork).

## Known design tensions (flag anything worse)

- The incremental side can only ever coarsen (attach adds mass, never
  nodes), so metric 2 partially measures "old tree is coarser than new
  tree" rather than "old tree is wrong." Matched-granularity comparison
  mitigates but does not eliminate this.
- Temporal arrival confounds order with content non-stationarity
  (ai-building's known mixture shift) — that is the point of the random-
  order contrast, but n=1 temporal path per bucket.
- 50% base fraction is one choice; if it matters, say so and we add a
  base-fraction sensitivity arm.
- visual-craft at 86 notes: checkpoints are small; expect noise.

## Questions

1. Is the three-metric battery decision-grade for choosing theta, or is
   something missing (e.g., a legibility-proxy metric closer to what E7
   measured)?
2. Is the policy grid {0.10, 0.25, 0.50, never} the right menu?
3. Any objection to running per-cell in parallel agents (same script,
   different params, JSON artifacts merged afterward)?

Respond in `docs/grove-lab/path-dependence-design-review-codex.md` with
ONE fenced JSON block: {"verdict": "run|run-with-changes|redesign",
"findings": [{"id","severity","argument","required_change"}],
"answers": {"q1","q2","q3"}}.
