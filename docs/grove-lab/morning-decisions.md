# Morning decisions — grove path dependence and follow-ons

2026-07-13. Each item: options, a recommendation, and the artifact that
backs it. Full analysis: `path-dependence-report.md`.

> **STATUS AFTER CODEX v6 (`external-review-response-codex-v6.md`): items
> (a) and (b) were HELD.** The v5 correction pass fixed findings locally
> but broke grid comparability: the K2 centroid fix changed a SHARED
> engine helper, only cm + hybrid cells were rerun, and new-engine cells
> were compared against old-engine cells (proof: epicmap date-0.5 pure
> vs hybrid have identical trigger schedules, 3 rebuilds each, but
> different AUCs, 0.913 vs 0.927). The hybrid cells also use descendant
> centroids that production does not have. The meta-lesson stands
> recorded: review compliance is not experimental validity.
>
> **STATUS AFTER REPLAY v3 (`path-dependence-v3-addendum.md`,
> `replay-cells-v3/*.json`, 192 cells, one engine at `e0e903c`,
> production-faithful centroid semantics stamped per cell): item (a)'s
> measurement prerequisites are MET** — the v2 ranking holds under one
> engine, persistence staleness is measured (large under never-rebuild),
> and terminal-only attach is tested (material improvement, not a
> substitute for rebuilds). What remains on (a) is engineering, not
> measurement. **Item (b) remains HELD** (fit_nodes null + schema work,
> unchanged by v3).

## (a) Shipping policy for the grove cache

Options measured (144 cells, `replay-cells/*.json`, frontier figure
`path-policy-frontier.png`):

| option | what the data says (post Codex-v5 corrections) |
|---|---|
| never (current) | Ordinal hierarchy stays high at base 0.5 (0.69-0.93 raw agreement) but reads much lower for young trees (base 0.25: 0.493/0.680/0.701). Flat assignment and girth drift badly: epicmap final ARI 0.085, matched-mass L1 0.685 at coverage 0.902. Renderer-visible. |
| centroid-maintain | Not recommended, on CORRECTED grounds: the overnight comparator had an init bug (K2), all 24 cells rerun with the fix. Corrected cm is a wash vs never (worse ARI 14/24, worse triplet 11/24) and theta=0.25 beats it decisively on every inspected arm (epicmap date ARI 0.074 vs 0.762). "Dominated in every cell" retracted; terminal-only attach untested. |
| theta=0.1 | Most best-or-tied arms in the grid (triplet AUC 13, assignment 14 — more than theta=0.25's 12/9, per K1 recount). 7 rebuilds per doubling. Date-arm epicmap transient shallower than theta=0.25 (0.277 vs 0.097); deeper on 3 of 5 random seeds. |
| theta=0.25 + floor 15 | Hybrid cells exist (`*-rebuild-0.25f15.json`) with date-arm triplet AUC 0.927/0.972/0.916 and rebuilds 3/3/2 (v6 finding 7 corrected — earlier stated numbers were copy-forwarded from pure-theta cells). CAVEAT: these cells ran on post-K2 descendant-centroid semantics that production does not have (v6 finding 1). RESOLVED by replay v3: under one engine the date-arm triplet AUCs read 0.913/0.969/0.916 (the old engine flattered epicmap by ~0.014) and f15 is identical to pure 0.25 in 17/24 arms, all divergences confined to visual-craft where the floor suppresses one rebuild as designed (`replay-cells-v3/*-rebuild-0.25f15.json`, addendum section 1). |
| theta=0.5, 1.0 | Trigger-position artifacts. theta=0.5: one fire then a 517-note stale tail, final ARI 0.076. theta=1.0: fires at the very end, one deep dip (worst-pre 0.175). Final numbers flatter to deceive. Report section 2. |

**Recommendation: theta=0.25 + floor 15, measurement complete — shipping
now gates on engineering only.** Replay v3
(`path-dependence-v3-addendum.md`, all claims traceable to
`replay-cells-v3/*.json`) discharged the three measurement prerequisites:

1. **Ranking holds under one engine.** Best-or-tied over 24 arms:
   theta=0.1 leads AUC counts (ARI-AUC 14, triplet-AUC 14) vs theta=0.25
   (9, 13); never is best in ZERO arms on every metric; theta=1.0's
   final-checkpoint wins remain trigger-position artifacts (ARI-AUC grid
   mean 0.628, worst transient 0.058). 0.25+f15 is now genuinely
   comparable to pure 0.25: identical in 17/24 arms; all seven divergences
   are visual-craft, where the floor suppresses one rebuild as designed
   (bounded cost, worst final ARI -0.217 on n=86). The 0.25-vs-0.1 choice
   remains the 3-vs-7-rebuilds churn judgment.
2. **Persistence staleness measured (v6 finding 3): the held-out visual
   channel is genuinely stale under never.** Final-checkpoint matched-node
   branch-length L1 0.22-0.32 of tree-max under never-rebuild, with rank
   order collapsing (Spearman 0.023 ai-building, -0.200 visual-craft);
   theta arms hold L1 at 0.01-0.11, Spearman 0.77-0.94. Only rebuilds
   repair this channel — neither cm nor terminal attach touches it.
3. **Terminal-only attach tested (v6 finding 9): material, prominent, but
   it does NOT change the recommendation.** Production attach files
   27.6-37.8% of notes at internal nodes/root (`attach_internal_targets`);
   forbidding that beats production attach in 23/24 arms and recovers
   roughly 27% of the never-to-theta final-ARI gap, 43% of mass L1, 52%
   of ARI-AUC (grid means 0.368 -> 0.484 ARI, 0.411 -> 0.269 L1). It is a
   cheap, strictly local improvement worth shipping ALONGSIDE the rebuild
   policy — not instead of it (remaining drift still far from any theta
   arm; capacity starvation and persistence untouched). One confirmation
   arm (terminal attach between theta rebuilds) should run when it ships.
4. Corrected cm under one engine: wash on hierarchy/mass, mildly worse on
   assignment (ARI-AUC 5W/18L vs never). Closed — not recommended in any
   configuration.

**What remains before shipping — engineering, not measurement (v6 finding
2):** persistent debt state, snapshot schema migration, atomic snapshot
replacement, failure/concurrency behavior, and multi-invocation tests for
the automatic theta rebuild; plus the anchoring fix if continuity claims
are to be made (anchor_nodes matches direct members only and never anchors
internal nodes/root — v6 finding 8, still open). Known residual caveats:
the date arm is still not ingest order (`ingested_at` capture landed in
`922ff01` but history accrues from now), and AUC is still an unweighted
checkpoint mean.

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

**Recommendation: HELD (v6).** The construct is right and the numbers
stand as RAW agreement values, but two gaps before stamping: (1)
`fit_nodes_triplet` has no null of its own — the reported structure null
is full-linkage; a truncated-tree null with fixed label-count marginals is
needed before 0.622/0.742/0.947 count as calibrated evidence (v6 finding
4); (2) the ten-seed brackets are triplet-sampling min/max on ONE fixed
temporal split, not stability uncertainty — label accordingly, and report
dated-note counts (the top-level n includes undated notes the halves
omit; v6 finding 5). Integration is also not mechanical: stability schema
version, snapshot migration, frontend type + hub test changes, and import
restructuring (dendro must not import replay; v6 finding 6).

## (c) Bucket hygiene (you author buckets; these are flags, not edits)

From `bucket-quality.json`:

- **mind-systems reads like a centroid magnet — suggestive, not
  established** (v6 finding 11): nearest-other for 5 of 9 buckets, but
  that could be residual-category breadth, small-sample centroid noise,
  or embedding-space anisotropy. Leave-one-out assignment counts (how
  many notes would actually transfer) are needed before restructuring.
- **Tiny buckets**: eating (4), film (3), adhd (2) show the largest
  nominal separations (0.078-0.108) — but within-similarity is computed
  against a centroid containing the point itself, which flatters n=2-4
  badly (v6 finding 10: adhd's 0.980 is not evidence of coherence).
  Treat as exploratory; leave-one-out estimates needed before any merge
  decision leans on these numbers.
- **Separations are uniformly thin** (0.02-0.11 against within-sim ~0.9),
  epicmap/ai-building/visual-craft included; bucket identity comes from
  your rules, not embedding geometry. No overlap notes (0 match 2+
  buckets), so the rules are at least crisp.
- **41% unmatched (1805 of 4449) — a fact, not automatically a defect**
  (v6 finding 13): the grove may intentionally model only authored
  interests. Before calling it a hole, characterize the unmatched mass by
  source/project/date/nearest-bucket; the product question is whether
  important topics are absent, not whether every note grows a leaf.
- Dedupe reconciliation is in the same file: 168 duplicate keys, 169 rows
  removed at resolve time. Store-level fix remains issue #71.

## (d) Next build tracks (E7 passed its committed band: `e7-results.json`
— identification 6/6, adjacency and primary readback clean; visual-craft
payload the one "no read"; topology invariance 7/9 with binomial tail
0.0898, i.e. marginal, and secondary readback 4/6)

1. **Terminal-only attachment BEFORE split-on-mass** (reordered per v6
   finding 9): production attach searches every node centroid including
   the root and internal limbs, but fresh fits assign notes to terminal
   nodes only — incremental labels can exist that no fresh derivation
   would ever produce, a cheap-to-test candidate mechanism for the ARI
   drift. Test order: production attach as-is; terminal-only; terminal-
   only + maintained centroids; periodic rebuild; split-on-mass last.
   All against the replay v3 harness on identical cells.
2. **Ingest-date capture — next, but not a one-liner** (v6 finding 15):
   consistent across every ingestion path, immutable under re-embedding
   and reindexing, distinguished from update time, timezone-defined,
   backward-compatible. Worth doing immediately BECAUSE it cannot be done
   retroactively; scope it as a small feature, not a line.
3. **Glow wires + cosine palettes — proceed as product work** (v6 finding
   16 wording): the personal readback result earned continued development
   of the form. Not because measurement is "done" — the cache policy is
   unshipped, persistence drift unmeasured, and E7 was one owner, three
   primary trials, one renderer. Build the shaders on the strength of an
   encouraging personal result, with the science continuing alongside.

Suggested order after v6: (d.3) shaders may start immediately as product
work; (d.2) ingest-date capture same day, scoped honestly; replay v3
(one engine, persistence metric, terminal-only arm) is the next science
session and gates (a); the fit_nodes null and schema work gate (b).
