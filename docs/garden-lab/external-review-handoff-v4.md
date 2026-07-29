# External review handoff v4: re-audit for clear_to_run

Your v3 response (`external-review-response-codex-v3.md`) blocked the run
on H1-H4 and rejected A1. All eight findings are addressed; this round is
a verification pass. Repo access assumed; tests:
`uv run --extra dev pytest tests/ -q` (424 green).

## Finding-by-finding disposition

- **H1 (critical, truth leak via stimulus ids): fixed.**
  `build_manifest` now returns (public, key). Public stimuli carry opaque
  ids `s00..sNN` (seeded permutation over creation order); answers + the
  opaque-to-private map live only in `~/.ytk/grove/e7-answer-key.json`,
  which no serving code path reads. The `anchor` trial field is renamed
  `top`. Test `test_public_manifest_leaks_no_roles` greps the serialized
  public manifest for `ctrl`, `rerender`, `"answer"` and asserts opaque
  id shape. Live check on the shipped hub: leaks=False.
- **H2 (critical, ordering contamination): fixed.** Explicit blocks:
  practice -> each bucket's first task-1 exposure (randomized bucket
  order, marked `primary`) -> task-1 repeats -> task 2 -> exploratory
  identification strictly last. Randomization only within blocks.
  `test_blocks_isolate_primary_exposures` asserts primaries occupy scored
  positions 0-2 and T3 is terminal.
- **H3 (critical, response integrity): fixed.** Server: pydantic bounds
  (confidence 1-5, rt_ms >= 0), unknown trial -> 404, choice validated
  against the trial's allowed set (left/right or its `options`) -> 400,
  idempotency by manifest sha + trial (exact duplicate acknowledged
  without append; conflicting duplicate -> 409), GET returns `completed`
  for resume. UI: submit lock, advance only on confirmed persistence
  (409 also advances - the trial is already recorded), retry state on
  network failure, resume from server state on load. Tests:
  `test_e7_post_validates_and_is_idempotent`,
  `test_e7_post_rejects_invalid_trials_choices_and_bounds`,
  `test_e7_get_serves_manifest_with_completed_list`.
- **H4 (major, RT/readiness): fixed.** Each StimulusCanvas reports ready
  after scene creation + data planting; choices stay hidden behind a
  "growing..." state until every canvas in the trial is ready plus a
  900ms growth interval; RT starts at reveal. Trial index resolves only
  after manifest load (resume), so trial zero cannot start timing during
  fetch.
- **H5 (major, A1 rejected): accepted and implemented.** Explicit
  `camera_azimuth` per stimulus, rotated in the scene
  (`scene.ts` camera placement from `payload.azimuth`). Task-1 pairs
  share geometry seed AND azimuth (only structure differs; verified by
  `test_task1_pairs_share_geometry_and_azimuth_task2_distinct`); task-2
  stimuli carry three distinct geometry seeds. Preregistration amendment
  1 retracted, replaced by amendment 4.
- **H6 (major, repetition learning): implemented** via the primary flag +
  block placement; preregistration now names the three primaries as the
  only uncontaminated semantic observations and demotes repeats to
  secondary learning/consistency data. The 7/9 band no longer stands
  alone; per-primary outcomes are reported first.
- **H7 (minor, unverified balance): fixed.** Left/right assignment is
  drawn from a balanced multiset per task group;
  `test_left_right_balance_within_pair_blocks` asserts |L-R| <= 1.
- **H8 (minor, visual-craft construct): implemented.** The control
  generator prefers adjacency-breaking draws and falls back to
  payload-only; each task-1 trial carries `construct: adjacency|payload`
  (`test_visual_craft_is_payload_construct`), and payload trials are
  preregistered as payload-geometry readback, unpooled.

Manifest regenerated with a new seed (72) after all fixes; the prior
manifest was never run past the practice block, so the subject remains
naive. Live hub verification: 26 trials, opaque ids, no leak markers,
primaries at scored positions 0-2, `completed: []`.

## Files for this audit

- `scripts/grove_lab/e7_manifest.py` (generator), `tests/test_grove_e7.py`
- `ytk/ui/server.py` (`/api/grove/e7*`), e7 tests at the end of `tests/test_hub.py`
- `web/src/routes/grove.tsx` (`ReadbackPage`, `StimulusCanvas`),
  `web/src/lib/grove/scene.ts` (azimuth), `web/src/lib/grove/datatree.ts` (payload type)
- `docs/grove-lab/e7-preregistration.md` (amendments 4-9)

## One residual to weigh

Matched geometry seeds make task-1 pairs visually twin-like except for
structure — by design. On the small practice trees the difference is
subtle; on 13-15-node scored topologies it is larger. If you judge the
practice pairs too subtle to teach the interface, say so — practice
stimuli can be made coarser without touching scored stimuli.

## Output format

ONE fenced JSON block:

```json
{
  "verdict": {
    "clear_to_run": true,
    "summary": "<= 3 sentences"
  },
  "findings": [
    {"id": "J1", "severity": "critical | major | minor",
     "target": "manifest | endpoint | trial-ui | protocol",
     "argument": "...", "evidence_or_repro": "...",
     "required_change": "...", "confidence": 0.0}
  ]
}
```

If nothing blocks, return an empty findings array and clear_to_run true.
