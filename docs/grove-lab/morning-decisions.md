# Morning decisions — grove path dependence and follow-ons

2026-07-13. Each item: options, a recommendation, and the artifact that
backs it. Full analysis: `path-dependence-report.md`.

> **STATUS AFTER CODEX v6 (`external-review-response-codex-v6.md`): items
> (a) and (b) are HELD.** The v5 correction pass fixed findings locally
> but broke grid comparability: the K2 centroid fix changed a SHARED
> engine helper, only cm + hybrid cells were rerun, and new-engine cells
> were compared against old-engine cells (proof: epicmap date-0.5 pure
> vs hybrid have identical trigger schedules, 3 rebuilds each, but
> different AUCs, 0.913 vs 0.927). The hybrid cells also use descendant
> centroids that production does not have. Nothing below ships until a
> replay v3 reruns the comparable grid under ONE engine with
> production-faithful semantics, adds a persistence-staleness metric, and
> tests terminal-only attachment. The meta-lesson stands recorded: review
> compliance is not experimental validity.

## (a) Shipping policy for the grove cache

Options measured (144 cells, `replay-cells/*.json`, frontier figure
`path-policy-frontier.png`):

| option | what the data says (post Codex-v5 corrections) |
|---|---|
| never (current) | Ordinal hierarchy stays high at base 0.5 (0.69-0.93 raw agreement) but reads much lower for young trees (base 0.25: 0.493/0.680/0.701). Flat assignment and girth drift badly: epicmap final ARI 0.085, matched-mass L1 0.685 at coverage 0.902. Renderer-visible. |
| centroid-maintain | Not recommended, on CORRECTED grounds: the overnight comparator had an init bug (K2), all 24 cells rerun with the fix. Corrected cm is a wash vs never (worse ARI 14/24, worse triplet 11/24) and theta=0.25 beats it decisively on every inspected arm (epicmap date ARI 0.074 vs 0.762). "Dominated in every cell" retracted; terminal-only attach untested. |
| theta=0.1 | Most best-or-tied arms in the grid (triplet AUC 13, assignment 14 — more than theta=0.25's 12/9, per K1 recount). 7 rebuilds per doubling. Date-arm epicmap transient shallower than theta=0.25 (0.277 vs 0.097); deeper on 3 of 5 random seeds. |
| theta=0.25 + floor 15 | Hybrid cells exist (`*-rebuild-0.25f15.json`) with date-arm triplet AUC 0.927/0.972/0.916 and rebuilds 3/3/2 (v6 finding 7 corrected — earlier stated numbers were copy-forwarded from pure-theta cells). CAVEAT: these cells run on post-K2 descendant-centroid semantics that production does not have, and the pure-theta cells they were compared to ran on the older engine — "identical in 12/18 arms" described trigger schedules only, not measured behavior (v6 finding 1). Not comparable until replay v3. |
| theta=0.5, 1.0 | Trigger-position artifacts. theta=0.5: one fire then a 517-note stale tail, final ARI 0.076. theta=1.0: fires at the very end, one deep dip (worst-pre 0.175). Final numbers flatter to deceive. Report section 2. |

**Recommendation: HELD (v6).** theta=0.25 + floor remains the leading
candidate, but shipping requires: (1) replay v3 — one engine version,
production-faithful centroid semantics, full comparable grid, artifacts
stamped with schema + git commit; (2) a persistence-staleness metric
(branch LENGTH is a principal visual encoding and attach never updates
persistence — unmeasured, v6 finding 3); (3) the terminal-only attach
comparator (v6 finding 9 — production attach can file notes at internal
nodes/root, which fresh fits never do; possibly a major drift mechanism
and cheaper than split-on-mass); (4) honest engineering scope — automatic
rebuild needs persistent debt state, snapshot migration, atomic
replacement, and multi-invocation tests; it is NOT a small mechanical
change (v6 finding 2). Also: the continuity-cost judgment cannot even be
supported by current anchoring, which matches direct members only and
never anchors internal nodes (v6 finding 8).

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
