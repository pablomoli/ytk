# Encoder audit — report 4: synthesis and recommendation

2026-07-16 · issue #73 · synthesizes reports 0-3
(3 deep-research passes: 309 agents, ~10.7M tokens, 64 sources fetched,
329 claims extracted, 75 adversarially verified, 6 refuted)

## Recommendation

**Do not migrate yet. Run a staged trial with Qwen3-Embedding-0.6B as the
primary candidate, and let the harness decide.** The research killed the two
lazy arguments: "everyone uses something better" is false (Khoj defaults to
our exact encoder), and "the leaderboard says +9 points" is unreliable
(version-conflated, vendor-reported, contamination-inflated by the
maintainers' own admission). What remains is a genuinely promising candidate
whose decisive properties — on-corpus retrieval quality, clustering geometry,
M3 throughput, 384-dim truncation loss — are unmeasured. Measuring them is
cheap. Migrating without measuring them would repeat the mistake the grove
experiments taught us not to make.

Independent of the encoder decision, three pipeline fixes are justified now:

1. **#71** — phantom double-indexed vectors: hygiene prerequisite for any eval.
2. **#84** — memories truncate at 512 tokens: apply the contextual-parts
   strategy (already proven on videos, and independently validated by
   Anthropic's contextual-retrieval numbers) OR fold into migration if a
   long-context model wins. Decide with the harness, fix within the month.
3. **Chunk regimes per bucket** — transcripts keep small segments (fact
   lookup); memories/notes get broader chunks. Chunking is the largest
   measured lever in the entire literature review — bigger than the model swap.

## Why Qwen3-Embedding-0.6B is the candidate

Apache-2.0, 32k context (structurally eliminates #84's failure class),
MRL-native with user-set dims including our exact 384, instruction-aware,
sentence-transformers-compatible (one-line `_TEXT_MODEL` change + re-embed),
MTEB v2 70.70 mean at 0.6B — tying a 7.6B model. Controls in the trial:
bge-small-en-v1.5 (384-dim drop-in, isolates "any migration" from "this
migration"), the incumbent (baseline), optionally bge-m3 (mid-size control).
Card-check EmbeddingGemma and gte-modernbert before locking the shortlist.

Known risks: clustering is Qwen3-0.6B's weakest category (54.05 vs 58.97 for
larger models) and clustering geometry is what grove/map/galaxy consume; ~18x
incumbent params (throughput unmeasured on M3); vendor-reported scores;
prefix contract may interact badly with clustering (BGE ablation: clustering
prefers no-instruct).

## The eval harness (issue #73's deliverable, now specified)

Gate 0 — hygiene: #71 fixed; vector/file reconciliation clean (report 0 found
4,521 vectors vs ~3,539 files in ytk_memories); stamp every artifact with
commit + model id.

Gate 1 — known-item retrieval (the product metric):
- Generate ~150-300 synthetic "half-remembered" queries with an LLM from held
  notes across all three buckets (videos/segments/memories), in the user's
  actual query register ("how did that guy use the television CLI?").
- Metric: hit@1/5/10 per bucket, incumbent vs candidates, full dims and
  384-MRL truncation.
- Validity of synthetic queries is itself unproven (pass B open question) —
  so also replay the real query log if available, and spot-check 20 queries
  by hand.

Gate 2 — geometry stability (the visualization metric):
- Triplet agreement against user-authored buckets (grove discipline), k-NN
  neighborhood preservation (Jaccard@k) between incumbent and candidate
  spaces, Procrustes distance across re-embeds.
- 20+ seeds, paired intervals, never flat ARI (memory: agglo-vs-hdbscan
  lesson). New metrics get their own null distributions.
- UMAP faithfulness at 64/128/384 dims: neighborhood preservation of the 2D
  map per input dim — the literature is silent; we measure.

Gate 3 — operational:
- Wall-clock re-embed of all 7,832 docs on M3 (MPS and MLX paths; pass A
  found zero verified throughput numbers — 20-minute local benchmark).
- Peak RAM alongside running hub; cold-start latency for first query.

Decision rule: migrate only if Gate 1 improves by a margin that survives
paired intervals AND Gate 2 does not regress AND Gate 3 is livable. If Gate 1
wins but Gate 2 regresses, consider dual-track: candidate for search,
incumbent (or prefix-free variant) for visualization geometry — measured, not
assumed.

Migration day, if it comes: one stamped pass — re-embed everything, re-fit
the map's UMAP params, re-run grove gates, reprice #83's interest snapshots
(or pin theme identity via a TTEC-style frozen compass, report 3), regenerate
web bundles. Never let two encoders' geometries coexist silently.

## What stays decided without further research

- **Local-first stays.** The entire competitive field validates it; Apple's
  platform trajectory (NLContextualEmbedding → Foundation Models
  semantic-search APIs → Core AI) strengthens it, and offers a future
  zero-hosting mobile path (#82).
- **Text/image spaces stay disjoint** until a measured reason to bridge
  appears (all unification claims failed verification).
- **The interest market (#83) does not wait for the encoder** — it reads
  interest snapshots, not raw vectors. TTEC-style compass alignment or pinned
  theme centroids solve ticker identity under any future re-embed.
- **Prefix adoption is conditional**: only if the winning model contracts for
  it, and with a clustering-impact check first.

## Cost of certainty

Three passes: 309 agents, ~10.7M tokens, 75 claims triple-verified, 6
plausible-sounding claims killed (each one would have misled the design —
notably arctic's fake 8k context and late-chunking-as-free-lunch). The
refutations alone justified the adversarial pass.

## Open threads carried forward

- Local: throughput benchmark, 384-truncation curve on our corpus, UMAP
  faithfulness experiment, synthetic-query validation → all inside the #73
  harness.
- Research: mymind/Tana/Fabric/Limitless current stacks (nothing survived);
  graph-view reception; jina-v3/v4, EmbeddingGemma, stella, gte-modernbert
  card sweep → #74 and harness setup.
- Product: #83 prior-art leads (ThemeRiver, streamgraph/last.fm, Spotify
  Wrapped phases, arXiv:1912.09210 drift angle, TTEC) logged on the issue.
