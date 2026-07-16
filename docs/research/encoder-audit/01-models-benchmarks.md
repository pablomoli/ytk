# Encoder audit — report 1: candidate models and benchmark state

2026-07-16 · issue #73 · deep-research pass A
100 agents · 18 sources · 90 claims extracted · 25 verified (23 confirmed, 2 refuted 0-3)

## Verdict of this pass

Credible locally-runnable replacements exist, and the evidence *tentatively*
justifies migration — with one standout candidate — but the decisive numbers
(on-corpus quality, M3 throughput, truncation loss) are not in the literature
and must come from our own eval harness. That is not a gap in the research;
it is the finding.

## The standout: Qwen3-Embedding-0.6B (June 2025)

| Property | Value | Why it matters for ytk |
|---|---|---|
| License | Apache-2.0 | clean |
| Params / footprint | 0.6B, ~1.2 GB fp16 | fits M3 16GB beside hub + Chroma (to be measured) |
| Context | 32k tokens | structurally fixes #84 — memories, and even long source notes, embed whole; video parts strategy could simplify |
| Dims | Matryoshka, user-set 32-1024 | can emit exactly 384 — ytk's schema width unchanged (still a full re-embed: different space) |
| Instruction-aware | yes | asymmetric query/doc prompts (pass B topic) |
| MTEB English v2 | 70.70 mean, 61.83 retrieval, 86.57 STS, 54.05 clustering | essentially ties gte-Qwen2-7B-instruct (70.72) at 1/12 the params; beats NV-Embed-v2 (7B) |
| MMTEB multilingual | 64.33 | beats BGE-M3 (59.56), me5-large-instruct (63.22) |
| sentence-transformers | supported per model card | one-line `_TEXT_MODEL` change + re-embed |

Caveats attached by the verifiers: all scores are vendor self-reported,
instruction-prompted, with baselines copied from a May 2025 leaderboard
snapshot rather than re-run. Per-category the "tie" breaks down — 0.6B wins
retrieval/STS but loses clustering (54.05 vs 58.97), and clustering is what
grove/map/galaxy geometry leans on. Sized against the incumbent it is ~18x
the parameters; throughput must be measured, not assumed.

## The incumbent, honestly measured

thenlper/gte-small: 33.4M params, ~70 MB, 384-dim, 512-token max, English
only. MTEB **v1**: 61.36 avg / 49.46 retrieval / 82.07 STS / 44.89 clustering.
The headline ~9-point mean / ~12-point retrieval gap to Qwen3-0.6B **conflates
benchmark versions** — gte-small has no verified MTEB v2 score, and this was
the pass's only 2-1 split vote. Directionally reliable, not exact. The eval
harness should rescore gte-small on MTEB(eng, v2) (or at least a task subset)
to put both models on one ruler.

## Mid-size candidates (all force schema changes)

- **BGE-M3** (Feb 2024, MIT): most frictionless mid-size path — literal
  one-line change via sentence-transformers (dense mode is all we use). But
  1024-dim (2.67x vector storage), 568M params (~2.3 GB fp32), 8192-token
  context, and it trails Qwen3-0.6B on MMTEB (59.56 vs 64.33).
- **snowflake-arctic-embed-l-v2.0** (Nov 2024, Apache-2.0): retrieval-focused,
  568M/1024-dim, self-reports BEIR-15 55.6 vs bge-m3's 48.8. Two flags: the
  card's own table shows the OLDER arctic v1 slightly ahead on BEIR (56.0),
  and the claim that it has 8192-token bge-m3-lineage context was **refuted
  0-3** — do not assume its context behavior.
- **nomic-embed-text-v2-moe** (Feb 2025): 475M/305M-active MoE, 768-dim
  truncatable to 256 (MRL), ~100 languages. Its 512-token max is a
  **regression** vs nomic v1.5's 8192 — wrong direction for our transcripts.
- **bge-small-en-v1.5** (Sept 2023, MIT): the only exact 384-dim/33M drop-in,
  but same vintage and size class as gte-small — at best marginal gain; a
  low-disruption fallback, not a target.

## How to read the leaderboards (verified, and sobering)

- MMTEB (ICLR 2025) ships a zero-shot English track and per-model zero-shot
  scores because — maintainers' own words — "the highest ranking models
  achieve their scores by training on benchmark tasks, even though models with
  lower scores might generalize better."
- The default leaderboard view still mixes contaminated and zero-shot models
  (`zero_shot_setting='allow_all'` confirmed in live source); the zero-shot
  annotation must be checked manually, and it relies on self-reported training
  data (a lower bound on contamination).
- RTEB (Oct 2025) added private held-out sets to catch overfitting — and its
  private column was pulled in Jan 2026 because co-developer Voyage AI had
  structural access to the private data. Independent held-out validation is
  weaker today than it looked at launch.
- Two plausible-sounding claims in the source pool were refuted 0-3 by the
  verifiers (arctic's context lineage; me5-large-instruct as MMTEB's top
  public model). The skeptical posture is earned.

Net: leaderboard deltas justify *shortlisting*, never *migrating*. On-corpus
eval is the only decision-grade evidence — which matches the grove lesson
already in our memory.

## Coverage gaps (leads, not negatives)

No claims survived for jina-embeddings-v3/v4, EmbeddingGemma, stella,
gte-modernbert, modernbert-embed, granite-embedding, or Qwen3-Embedding-4B —
and the entire M-series throughput question came back empty (sources exist
but nothing survived verification). Throughput we can and should measure
ourselves — it's a 20-minute local benchmark, strictly better than any blog
number. EmbeddingGemma and gte-modernbert are worth a manual model-card check
during harness setup since both target exactly this size class.

## Open questions that become eval-harness line items

1. Qwen3-0.6B MRL-truncated to 384: how much retrieval/clustering quality is
   lost vs native 1024, on OUR corpus? (Also decides whether to keep 384 or
   re-index at 1024.)
2. Measured M3 re-embed throughput + RAM coexistence with the hub: Qwen3-0.6B
   (MPS/MLX/ONNX) vs bge-small vs incumbent, over the real 7,832 docs.
3. gte-small rescored on MTEB v2 subset for a one-ruler gap number.
4. Sweep the uncovered small candidates' cards (EmbeddingGemma,
   gte-modernbert) before locking the shortlist.

## Sources

Primary: huggingface.co/Qwen/Qwen3-Embedding-0.6B · arXiv:2506.05176 ·
qwenlm.github.io/blog/qwen3-embedding · huggingface.co/thenlper/gte-small ·
arXiv:2308.03281 (GTE) · huggingface.co/BAAI/bge-m3 · arXiv:2402.03216 ·
huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0 · arXiv:2412.04506 ·
huggingface.co/nomic-ai/nomic-embed-text-v2-moe · arXiv:2502.07972 ·
huggingface.co/BAAI/bge-small-en-v1.5 · arXiv:2502.13595 (MMTEB) ·
arXiv:2506.21182 (Maintaining MTEB) · huggingface.co/blog/rteb ·
sbert.net efficiency docs. Secondary/blog sources marked in the run log.
