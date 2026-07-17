# Encoder audit — report 5: local eval results

2026-07-16 · issue #73 · local harness run (`experiments/encoder_harness/`),
applying the gates and decision rule specified in report 4

## Setup

### Corpus

4,409 documents exported from the live store (`data/corpus.jsonl`):

| Bucket | Docs |
|---|---|
| memories | 3,704 |
| segments | 600 |
| videos | 105 |
| **Total** | **4,409** |

With the contextual-parts strategy the same corpus expands to 7,448 vectors;
without it, one vector per doc (4,409).

### Query set

156 synthetic "half-remembered" queries (`data/queries.jsonl`), LLM-generated
from held notes in the user's actual query register, each with a single gold
document:

| Bucket | Queries |
|---|---|
| memories | 79 |
| videos | 33 |
| segments | 44 |

An independent verification pass confirmed the set is internally consistent:
all 156 gold ids exist in the corpus, zero duplicates, zero query-vs-corpus
bucket mismatches.

### Spaces evaluated

Six spaces, all unit-norm, identical doc ids in identical order (verified
independently — no space silently dropped):

| Key | Model | Dims | Parts |
|---|---|---|---|
| gte-small | thenlper/gte-small (incumbent) | 384 | yes |
| bge-small | BAAI/bge-small-en-v1.5 | 384 | yes |
| qwen3-0.6b | Qwen/Qwen3-Embedding-0.6B | 1024 | no |
| qwen3-0.6b-384d | same, MRL-truncated | 384 | no |
| qwen3-0.6b-parts | Qwen/Qwen3-Embedding-0.6B | 1024 | yes |
| qwen3-0.6b-parts-384d | same, MRL-truncated | 384 | yes |

## Gate 1 — known-item retrieval

Metric: hit@k over the 156 queries. Deltas are paired bootstrap on hit@5 vs
the gte-small baseline; "significant" means the 95% CI excludes zero.

| Space | hit@1 | hit@5 | hit@10 | Δhit@5 vs baseline | 95% CI | Significant |
|---|---|---|---|---|---|---|
| gte-small (baseline) | 0.583 | 0.859 | 0.891 | — | — | — |
| bge-small | 0.545 | 0.833 | 0.872 | -0.025 | [-0.071, +0.019] | no |
| qwen3-0.6b | 0.712 | 0.923 | 0.955 | **+0.065** | [+0.026, +0.109] | **yes** |
| qwen3-0.6b-384d | 0.679 | 0.891 | 0.942 | +0.032 | [-0.006, +0.071] | no |
| qwen3-0.6b-parts | 0.692 | 0.910 | 0.949 | **+0.051** | [+0.013, +0.096] | **yes** |
| qwen3-0.6b-parts-384d | 0.673 | 0.878 | 0.936 | +0.020 | [-0.026, +0.064] | no |

Per-bucket hit@5:

| Space | memories (n=79) | videos (n=33) | segments (n=44) |
|---|---|---|---|
| gte-small | 0.835 | 0.939 | 0.841 |
| bge-small | 0.848 | 0.879 | 0.773 |
| qwen3-0.6b | 0.886 | 0.939 | 0.977 |
| qwen3-0.6b-384d | 0.835 | 0.939 | 0.955 |
| qwen3-0.6b-parts | 0.873 | 0.939 | 0.955 |
| qwen3-0.6b-parts-384d | 0.810 | 0.939 | 0.955 |

The largest gains are on segments (0.841 → 0.977 for qwen3 native) — the
fact-lookup bucket the product metric cares most about. Videos are saturated
and tied across nearly all spaces.

**Gate 1 verdict per the decision rule** ("improves by a margin that survives
paired intervals"): **pass for qwen3-0.6b native and qwen3-0.6b-parts; fail
for both 384d truncations and for bge-small.** The 384d point estimates are
positive but their CIs include zero — no claim of improvement is licensed at
384 dims.

## Gate 2 — geometry stability

Metric: triplet agreement against provenance categories (25 seeds, k=10),
plus k-NN Jaccard@10 overlap with the baseline space. Deltas are paired
across seeds.

| Space | Triplet mean | std | Δ vs baseline | 95% CI | Significant | kNN-Jaccard vs baseline |
|---|---|---|---|---|---|---|
| gte-small (baseline) | 0.758 | 0.005 | — | — | — | — |
| bge-small | 0.708 | 0.004 | **-0.050** | [-0.058, -0.043] | **yes (regression)** | 0.577 |
| qwen3-0.6b | 0.855 | 0.006 | **+0.097** | [+0.084, +0.104] | **yes** | 0.449 |
| qwen3-0.6b-384d | 0.846 | 0.005 | **+0.088** | [+0.079, +0.095] | **yes** | 0.436 |
| qwen3-0.6b-parts | 0.855 | 0.006 | **+0.097** | [+0.084, +0.105] | **yes** | 0.465 |
| qwen3-0.6b-parts-384d | 0.847 | 0.005 | **+0.089** | [+0.080, +0.097] | **yes** | 0.449 |

Two readings of this table:

- **Quality**: every qwen3 variant significantly improves triplet agreement
  over the incumbent (report 4 flagged clustering as Qwen3's weakest MTEB
  category; on this corpus, with these categories, the concern does not
  materialize). bge-small significantly regresses.
- **Continuity**: kNN-Jaccard ~0.44–0.47 means fewer than half of each doc's
  10 nearest neighbors survive the swap. The map/grove/galaxy geometry will
  move substantially. This is expected for any real model change and is what
  report 4's migration-day protocol (re-fit UMAP, re-run grove gates) exists
  for — it is not a regression, but it is not a free update either.

Caveats on the category labels: the eligible-category filter (>= 5 docs)
drops 10 docs, so categories sum to 4,399 not 4,409 — by design, verified.
More importantly, one category (proj-claude-mem, 3,342 docs) dominates the
label distribution; triplet agreement here measures separation of
provenance-based groups, not topical structure. Procrustes stability across
re-embeds and the UMAP-faithfulness-per-dim experiment from the report 4 spec
were not run in this pass and carry forward.

**Gate 2 verdict** ("does not regress"): **pass for all four qwen3 variants
(significant improvement, not mere non-regression); fail for bge-small.**

## Gate 3 — operational (M3, 16 GB, MPS)

Full-corpus encode benchmarks (`data/*.bench.json`), all on `mps:0`:

| Space | Vectors | Load (s) | Encode (s) | Vec/s | Peak RSS (MB) |
|---|---|---|---|---|---|
| gte-small | 7,448 | 2.6 | 327 | 22.7 | 1,578 |
| bge-small | 7,448 | 6.5 | 311 | 23.9 | 1,011 |
| qwen3-0.6b | 4,409 | 1.4 | 2,190 | 2.0 | 2,812 |
| qwen3-0.6b-parts | 7,448 | 2.5 | 8,015 | 0.9 | 731 |

(The 384d rows are truncations of the native runs — same encode cost.)

Qwen3 is roughly 11–25x slower than the incumbent, as expected for ~18x the
parameters. Concretely, on the full 7,832-vector production surface:

- **One-time re-embed**: ~65 min (no-parts) to ~2.3 h (parts). Livable as a
  stamped one-time migration job.
- **Ongoing ingest**: ~0.5–1.1 s per vector, so a typical video (transcript
  segments + parts) adds on the order of a minute of encode time to an
  already-background ingest job. Livable.
- **RAM**: 2.8 GB peak (no-parts run) on a 16 GB machine that also runs the
  hub — tight but workable; the parts run peaked lower (731 MB) because it
  encodes short chunks.
- **Not measured**: single-query encode latency for interactive search, and
  the MLX path (only MPS was benchmarked). Query latency should be bounded by
  one short-text forward pass but was not observed directly.

**Gate 3 verdict** ("livable"): **pass, with the query-latency measurement
outstanding.** Nothing here blocks migration; the cost is a slower ingest
pipeline and a one-time multi-hour re-embed.

## Qwen3 native vs 384d vs parts

| Comparison | Result |
|---|---|
| native (1024d) vs 384d MRL | Truncation costs consistently: hit@5 0.923 → 0.891, hit@1 0.712 → 0.679, triplet 0.855 → 0.846. Verified: 384d never outperforms native on any metric or bucket. Decisively, the 384d retrieval delta vs baseline loses significance — the drop-in-dims path does not clear Gate 1. |
| parts (1024d) vs native no-parts | Native edges parts on overall hit@5 (0.923 vs 0.910), memories (0.886 vs 0.873), and segments (0.977 vs 0.954); geometry is a wash (0.855 both). With a 32k context window the model embeds whole documents well enough that the contextual-parts strategy — necessary under the incumbent's 512-token window — buys nothing here and costs ~3.7x the encode time. This also resolves #84's failure class structurally rather than via chunking. |
| parts-384d | Never outperforms parts (verified) — same MRL-truncation pattern. |

The geometric consistency of both truncation orderings (MRL keeps the
coarse directions, sheds fine detail) was independently verified, which
raises confidence that the run is measuring real structure rather than noise.

## Verification caveats

An independent verification pass returned `trustworthy: true, issues: []`.
Its material notes, plus honest limits of the design:

- Query set internally consistent (counts, gold ids, buckets) — verified
  programmatically. But the queries are **synthetic**; report 4 flagged
  synthetic-query validity as unproven. No real-query-log replay or manual
  spot-check happened in this pass.
- No NaN/degenerate metrics; all vectors finite and unit-norm; no hit rate
  pinned at 0 or 1.
- All CIs well-ordered; every `significant` flag matches its CI; bootstrap
  delta means match observed differences to within resampling noise.
- Geometry categories are provenance labels dominated by one project;
  triplet agreement against them is a proxy, not ground truth for topical
  clustering. Procrustes and UMAP-faithfulness gates from the spec were not
  run.
- Single machine, single run per space; 156 queries is at the low end of the
  spec's 150–300 range, and the videos bucket (n=33) is saturated and
  uninformative.

## What this means

Applying report 4's rule — migrate only if Gate 1 improves with paired-CI
support AND Gate 2 does not regress AND Gate 3 is livable:

- **qwen3-0.6b at native 1024 dims clears all three gates.** Gate 1: +6.5pt
  hit@5, CI excludes zero. Gate 2: +9.7pt triplet agreement, CI excludes
  zero. Gate 3: livable with a slower ingest pipeline and a ~1–2 h one-time
  re-embed. The dual-track contingency (candidate for search, incumbent for
  geometry) is unnecessary — the same space wins both.
- **The 384d drop-in path does not clear the bar.** Its retrieval CI includes
  zero. Migrating means adopting 1024 dims (new collections, larger store),
  not swapping the model behind the existing 384-dim schema.
- **The parts strategy should be dropped for the new model**, not ported:
  native whole-document embedding matches or beats it at a third of the
  encode cost, and the 32k window eliminates #84's truncation problem.
- **bge-small is eliminated** — no retrieval gain and a significant geometry
  regression. This also answers the "any migration vs this migration"
  control: the gains are specific to qwen3, not to re-embedding per se.

The evidence supports migrating to Qwen3-Embedding-0.6B at native dims,
conditional on closing two cheap gaps first: a hand spot-check (or real-log
replay) to validate the synthetic queries, and a single-query latency
measurement for interactive search. If those hold, proceed via the report 4
migration-day protocol: one stamped pass — re-embed everything, re-fit the
map's UMAP params, re-run the grove gates, regenerate web bundles — and never
let the two geometries coexist silently.
