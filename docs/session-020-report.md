# Session 020 report — grove science sprint (2026-07-12 to 2026-07-14)

Full narrative postmortem lives in the repo:
`docs/postmortems/2026-07-13-grove-science-sprint.md`. This note is the
vault pointer with the essentials.

## What the sprint produced

- **E7 passed**: the grove is legible to its owner. 3/3 uncontaminated
  primary readback trials (confidence 4.67), 6/6 exploratory
  identification at 3.7s median vs 1/3 chance. Preregistered, four
  pre-run audit rounds, run exactly once. `docs/grove-lab/e7-results.json`.
- **Cache policy measured, not argued**: 384 replay cells across three
  grid generations; final 192-cell v3 grid under one stamped engine.
  never-rebuild drifts badly (assignment, girth, AND branch length —
  persistence L1 0.22-0.32 with rank collapse); theta=0.25 + 15-note
  floor + terminal-only attach is the recommendation; shipping gates on
  engineering (persistent debt state, migration, anchoring fix).
- **Shipped**: user-authored bucket axis (~/.ytk/grove_buckets.yaml),
  data-native renderer behind the "data trees" toggle, /api/grove,
  ingested_at capture (immutable, accrues from 2026-07-13), dedupe of
  168 phantom chroma rows (#71 for the store-level fix), variant UI
  removed.

## The four method failures (all caught by the Codex review loop)

1. 2-seed comparison shipped as a decisive result — retracted at 20 seeds.
2. Flat-ARI gate on a hierarchy product — replaced by triplet agreement
   with a structure null; partially REVERSED the verdict (hierarchies
   reproduce where flat partitions do not, epicmap included).
3. Centroid-maintenance comparator init bug — unfair rejection; fixed,
   rerun, same conclusion on honest grounds.
4. Version skew (deepest): fixing findings locally destroyed grid
   comparability; "review compliance is not experimental validity."
   Fixed by parameterized semantics + engine stamps + full v3 rerun.

## Standing next steps

- Engineering for cache policy (a): debt state, migration, atomicity,
  descendant-based anchoring; terminal-only attach alongside.
- Gate swap (b): held on a fit_nodes-specific null + schema work.
- Shader track: NEW session, brief at
  `docs/grove-lab/shader-brainstorm-handoff.md` (OpenAI brainstorm first).
- Bucket hygiene flags are exploratory only (leave-one-out needed).

## Memories written this sprint

map-groups-by-provenance-not-topic, grove-trees-are-cached-and-grow,
agglo-cosine-beats-hdbscan-native (retraction), epicmap-has-no-substructure
(corrected), e7-readback-cleared-to-run (results),
review-compliance-is-not-validity, feedback-workflow-agent-models.
