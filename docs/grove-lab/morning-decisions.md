# Morning decisions — grove path dependence and follow-ons

2026-07-13. Each item: options, a recommendation, and the artifact that
backs it. Full analysis: `path-dependence-report.md`.

## (a) Shipping policy for the grove cache

Options measured (144 cells, `replay-cells/*.json`, frontier figure
`path-policy-frontier.png`):

| option | what the data says (post Codex-v5 corrections) |
|---|---|
| never (current) | Ordinal hierarchy stays high at base 0.5 (0.69-0.93 raw agreement) but reads much lower for young trees (base 0.25: 0.493/0.680/0.701). Flat assignment and girth drift badly: epicmap final ARI 0.085, matched-mass L1 0.685 at coverage 0.902. Renderer-visible. |
| centroid-maintain | Not recommended, on CORRECTED grounds: the overnight comparator had an init bug (K2), all 24 cells rerun with the fix. Corrected cm is a wash vs never (worse ARI 14/24, worse triplet 11/24) and theta=0.25 beats it decisively on every inspected arm (epicmap date ARI 0.074 vs 0.762). "Dominated in every cell" retracted; terminal-only attach untested. |
| theta=0.1 | Most best-or-tied arms in the grid (triplet AUC 13, assignment 14 — more than theta=0.25's 12/9, per K1 recount). 7 rebuilds per doubling. Date-arm epicmap transient shallower than theta=0.25 (0.277 vs 0.097); deeper on 3 of 5 random seeds. |
| theta=0.25 + floor 15 | The MEASURED hybrid (24 cells, `*-rebuild-0.25f15.json`): identical to pure theta=0.25 in 12/18 base-0.5 arms; the floor's cost lands on the smallest bucket (visual-craft: one fewer rebuild, final ARI 1.000 -> 0.887, triplet 1.000 -> 0.960). Date-arm triplet AUC 0.913/0.969/0.953, mass L1 <= 0.16 at base 0.5, 3 rebuilds per doubling. |
| theta=0.5, 1.0 | Trigger-position artifacts. theta=0.5: one fire then a 517-note stale tail, final ARI 0.076. theta=1.0: fires at the very end, one deep dip (worst-pre 0.175). Final numbers flatter to deceive. Report section 2. |

**Recommendation: ship anchored rebuild at theta=0.25 with the 15-note
floor — as an operationally preferred provisional policy, not a measured
optimum** (K1 wording). theta=0.1 wins more arms outright; theta=0.25 is
preferred only under a continuity/churn judgment (3 rebuilds per doubling
vs 7 — renumbering risk and animation noise, asserted not measured). Both
constants ship as config, and the hybrid's behavior is now measured
including its floor (K6 resolved). No online centroid maintenance. Compute
cost is a non-issue (report section 5).

## (b) Gate swap, issue #72 — stamp snapshots with triplet gates

Codex v5 HELD the original stamp (K7: one half-split, one triplet draw,
wrong construct). `gate72.json` was regenerated decision-grade: 10
triplet-sampling seeds on the fixed temporal halves, tie/collision
accounting, and BOTH constructs explicitly named. The numbers:

| bucket | fit_nodes_triplet (the stored/rendered topology) | full_linkage_triplet | structure null |
|---|---|---|---|
| epicmap | 0.622 [0.611, 0.636] | 0.476 | 0.332 |
| ai-building | 0.742 [0.726, 0.755] | 0.612 | 0.338 |
| visual-craft | 0.947 [0.939, 0.954] | 0.664 | 0.320 |

**Recommendation: swap and stamp with `fit_nodes_triplet` as the primary
field** (it measures the truncated node topology snapshots actually
render), `full_linkage_triplet` recorded alongside, and the tie/usable
stats kept in the stamp — epicmap's gate carries heavy tie-rejection
(~18k usable of 40k), a shallow-tree property that belongs next to the
number. K7's conditions are met. Mechanical change in
`scripts/grove_lab/dendro.py` + re-stamp.

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
