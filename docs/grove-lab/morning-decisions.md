# Morning decisions — grove path dependence and follow-ons

2026-07-13. Each item: options, a recommendation, and the artifact that
backs it. Full analysis: `path-dependence-report.md`.

## (a) Shipping policy for the grove cache

Options measured (144 cells, `replay-cells/*.json`, frontier figure
`path-policy-frontier.png`):

| option | what the data says |
|---|---|
| never (current) | Hierarchy holds at base 0.5 (triplet at/above the cross-half floor except visual-craft date, 0.732 vs 0.738) but falls below floor in all three buckets at base 0.25 on the date arm (epicmap 0.493 vs 0.596). Flat assignment and girth drift badly: epicmap final ARI 0.085, mass-share L1 0.685. Renderer-visible. |
| centroid-maintain | Rejected: theta=0.25 dominates it in every cell. Worse than never on ~3/4 of arm pairs (visual-craft date triplet 0.732 -> 0.532; ai-building date ARI 0.625 -> 0.453), though it improves ~1/4 (repairs mass L1 on 4 of 5 ai-building random seeds). Report section 2. |
| theta=0.1 | Best ai-building AUC (0.950); on the date arm a shallower epicmap transient than theta=0.25 (worst-pre 0.277 vs 0.097; theta=0.5's 0.454 is shallower still but ends stale), mixed vs theta=0.25 on random seeds. 7 rebuilds per doubling. |
| theta=0.25 | Knee of the frontier: best/near-best triplet AUC everywhere (date 0.913/0.969/0.953), mass L1 <= 0.16 final on the date base-0.5 arm (max across all arms 0.246, ai-building seed 102), 3 rebuilds per doubling. |
| theta=0.5, 1.0 | Trigger-position artifacts. theta=0.5: one fire then a 517-note stale tail, final ARI 0.076 despite the shallowest epicmap worst-pre (0.454). theta=1.0: fires at the very end, one deep dip (worst-pre 0.175). Final numbers flatter to deceive. Report section 2. |

**Recommendation: ship anchored rebuild at theta=0.25** — fire when
attached_since_rebuild >= 0.25 * n_at_last_rebuild — with an absolute debt
floor (suggest 15 notes) so saplings and slow buckets do not churn, and NO
online centroid maintenance. Cost is a non-issue (epicmap worst case ~seconds
per rebuild; report section 5). If transient dips right before a rebuild ever
become user-visible, theta=0.1 is the paid upgrade (2x rebuilds) on the date
arm — on random arms its transients are mixed against theta=0.25 (deeper on
3 of 5 epicmap seeds) — and it is a config constant either way.

## (b) Gate swap, issue #72 — stamp snapshots with triplet gates

`gate72.json` has the numbers ready: epicmap 0.478, ai-building 0.616,
visual-craft 0.673 (temporal halves, structure nulls all ~0.33); the seven
saplings gate null. This replaces the construct-invalid centroid-transfer
ARI gate (retraction history: `e2-report.md` sections 7-8; metric validity:
`shootout-v3.json`).

**Recommendation: yes, swap and stamp now.** Two honesty notes for the
stamp: these are temporal-split gates, so they read lower than the
random-split floors in `shootout-v3.json` (0.596/0.752/0.738) — record
which split kind the stamp used (`kind` field already does); and epicmap's
0.478 vs null 0.33 is a real but modest margin, consistent with its known
blob-ness. Mechanical change in `scripts/grove_lab/dendro.py` + re-stamp.

## (c) Bucket hygiene (you author buckets; these are flags, not edits)

From `bucket-quality.json`:

- **mind-systems is a centroid magnet**: it is the nearest-other bucket for
  5 of 9 others (youtube-channel, combat-sports, eating, film, adhd). Its
  13 notes sit near everything reflective/meta. Consider whether it is a
  real topic or a residue category.
- **Tiny buckets**: eating (4), film (3), adhd (2) are well-separated for
  their size (separation 0.078-0.108, the largest in the table) but render
  as saplings forever at this rate. Merging them into mind-systems or a
  single "life" bucket is defensible either way — your call.
- **Separations are uniformly thin** (0.02-0.11 against within-sim ~0.9),
  epicmap/ai-building/visual-craft included; bucket identity comes from
  your rules, not embedding geometry. No overlap notes (0 match 2+
  buckets), so the rules are at least crisp.
- **Coverage is the bigger hole**: the same file records total_notes 4449
  vs matched 2644 — 1805 notes (41%) match no bucket at all. Crisp rules,
  but they see barely over half the vault.
- Dedupe reconciliation is in the same file: 168 duplicate keys, 169 rows
  removed at resolve time. Store-level fix remains issue #71.

## (d) Next build tracks (E7 passed its committed band: `e7-results.json`
— identification 6/6, adjacency and primary readback clean; visual-craft
payload the one "no read"; topology invariance 7/9 with binomial tail
0.0898, i.e. marginal, and secondary readback 4/6)

1. **Split-on-mass for attach** — evidence-backed for ai-building:
   capacity starvation is measured there (incremental tree frozen at
   7 nodes while fresh grows to 13;
   `replay-cells/ai-building-date-0.5-rebuild-never.json`). It is not the
   mechanism everywhere — epicmap's worst drifter has zero capacity gap
   (ref and incremental both 15 nodes, k_main 9 throughout) and even
   ai-building's matched-capacity reference agrees less on the date arm
   (0.290 vs 0.625), so much of that gap is genuine path dependence. A
   split rule attacks one measured mechanism, not the root cause across
   buckets; theta=0.25 (item a) is the containment either way. Natural
   sequencing: ship (a) now, prototype split-on-mass against the same
   replay harness (`scripts/grove_lab/replay.py`) so it must beat
   theta=0.25 on the identical cells to ship.
2. **Ingest-date capture** — write ingest timestamps at store time so the
   next replay's date arm is honest production arrival instead of a
   stress case (review P3; `e2-report.md` section 1 caveat). Cheap now,
   impossible retroactively.
3. **Glow wires + cosine palettes** — the shader/decoration track was
   deliberately blocked on measurement (`e2-report.md` section 9).
   Measurement is done: hierarchy is legible per E7 with the caveats in
   the header (visual-craft payload no-read, topology invariance
   marginal) and stable under the shipped cache + (a). Decoration is
   unblocked.

Suggested order: (a) and (b) are small mechanical changes this morning;
(d.2) is a one-liner worth doing the same day; (d.1) and (d.3) are the next
real sessions, in whichever order the mood favors.
