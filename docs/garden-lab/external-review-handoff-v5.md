# External review handoff v5: audit the overnight path-dependence study

Same contract as rounds 1-4. Your design review
(`path-dependence-design-review-codex.md`, verdict run-with-changes,
P1-P7) was applied in full and the study ran overnight as a 144-cell
orchestrated grid. This round audits the RESULTS and the recommendation
before two mechanical changes ship this morning. Repo access assumed;
tests `uv run --extra dev pytest tests/ -q` (432 green).

## What ran

- Engine: `scripts/grove_lab/replay.py` (v2 — verify your P1-P7 landed:
  debt semantics + event metrics P1, dual references P2, date-ordered arm
  with randomized ties/undated interleave P3, descendant-mass metric with
  coverage+L1 P4, triplet accounting + shared samples P5, base-fraction
  arms + centroid-maintain comparator P6, frozen inputs/refs +
  deterministic seeds + atomic outputs + work proxy P7). Unit tests in
  `tests/test_grove_replay.py` include exact trigger positions.
- Grid: 3 buckets x (date arm x base {0.25, 0.5, 0.75} + 5 random orders
  x base 0.5) x 6 policies = 144 cells in `docs/grove-lab/replay-cells/`
  (filename = bucket-order-base-policy-theta.json). All 144 present,
  hash-stamped, zero agent errors.
- Synthesis: `path-dependence-report.md` + `morning-decisions.md`,
  written by one agent, then attacked by three verifier agents (numbers /
  overclaim / completeness) which produced 19 corrections that a fixer
  applied. CAVEAT FOR YOU: the verifiers are same-family models reviewing
  same-family output — your independent audit is the real check.

## Claims to attack (the morning menu hangs on these)

C1. Grow-only attach preserves hierarchy ORDER: triplet agreement stays
    at/above each bucket's intrinsic cross-half floor at base 0.5, and
    the failure at base 0.25 (epicmap 0.493 vs floor 0.596) is the
    stated exception.
C2. Grow-only attach fails on renderer-visible quantities: epicmap
    never-rebuild final ARI 0.085, mass-share L1 0.685.
C3. Attribution: ai-building's drift is partly capacity starvation
    (frozen 7 nodes vs fresh 13) but epicmap's is not (both sides 15
    nodes, k_main 9 throughout); matched-capacity references support a
    genuine-path-dependence component.
C4. Centroid maintenance is REJECTED: theta=0.25 dominates it in every
    cell; it is worse than never on ~3/4 of arm pairs.
C5. theta=0.25 is the frontier knee (triplet AUC 0.913/0.969/0.953 on
    the date arm, final mass L1 <= 0.16 at base 0.5, 3 rebuilds per
    doubling) and the shipping recommendation, with a 15-note absolute
    debt floor.
C6. theta=0.5 and 1.0 final numbers are trigger-position artifacts (one
    late fire, stale tail or end-spike) and must not be read from final
    checkpoints alone.

## Weaknesses we already see (go further)

W1. One date-arm path per bucket (P3 acknowledged: it is a stress case,
    not production arrival; ingest-date capture is queued). The
    recommendation generalizes from date + 5 random arms.
W2. AUC averages different checkpoint counts at base 0.75 (3 checkpoints
    vs 5) — stated in the report, but cross-base AUC comparisons are
    accordingly soft.
W3. Triplet agreement can be null under the usable floor; nulls are
    dropped from AUC means, which can flatter cells with heavy tie
    rejection.
W4. Descendant-mass matching uses a 0.3 Jaccard cutoff; unmatched mass is
    reported but the cutoff itself is unswept.
W5. The 19 verify-pass corrections were applied by a fixer agent; spot-
    check that corrections were applied faithfully and none introduced a
    new error.
W6. The 15-note absolute debt floor in the recommendation is a suggestion
    (operational judgment), not a measured quantity.

## Files

`docs/grove-lab/`: path-dependence-report.md, morning-decisions.md,
replay-cells/*.json (144), path-divergence-{triplet,ari}.png,
path-policy-frontier.png, gate72.json, bucket-quality.json, plus prior
context (e2-report.md, shootout-v3.json, e7-results.json).
Engine + tests: `scripts/grove_lab/replay.py`, `tests/test_grove_replay.py`.
Frozen inputs/refs: `~/.ytk/grove/replay-{input,refs}/` (hash-stamped in
every cell).

## Output format

ONE fenced JSON block:

```json
{
  "verdict": {
    "results_valid": "yes | with-corrections | no",
    "theta_025_recommendation": "ship | ship-with-conditions | do-not-ship",
    "gate72_swap": "ship | hold",
    "summary": "<= 3 sentences"
  },
  "findings": [
    {"id": "K1", "severity": "critical | major | minor",
     "target": "C1..C6, W1..W6, engine, or 'new'",
     "argument": "...", "evidence_or_repro": "file or command",
     "required_change": "...", "confidence": 0.0}
  ],
  "answers": {
    "blocking_for_morning_ship": ["finding ids that must be resolved before shipping items (a)/(b), or empty"]
  }
}
```

Recompute, do not trust: the cells are small JSON; spot-verify the
report's numbers directly against them with python.
