# Encoder audit — report 2: pipeline techniques and label-free evaluation

2026-07-16 · issue #73 · deep-research pass B
104 agents · claims adversarially verified 3-0 unless noted · 4 popular claims refuted

## Verdict of this pass

Ranked by measured payoff for a personal corpus: **chunking strategy >
encoder choice > instruction prefixes**. And the three sub-questions that
matter most to ytk's visualizations — multimodal unification, zero-label eval
protocol, UMAP faithfulness — produced NO surviving verified claims. The
literature doesn't settle them; our own experiments must.

## 1. Asymmetric prefixes: a usage contract, a modest gain

- Prefixes (`search_query:` / `search_document:`) are task conditioning, not
  magic: without them, biencoders get conflicting training signal between
  similarity and retrieval objectives (Nomic, arXiv:2402.01613). For models
  that train with them, they are a **hard usage contract** — nomic-v1.5's card
  requires them.
- Measured isolated impact is modest: BGE's ablation shows +0.98 nDCG@10
  retrieval, +1.98 STS — and **clustering actually prefers no-instruct
  (-1.62)** (C-Pack, arXiv:2309.07597). Since grove/map/galaxy consume
  clustering geometry, prefixes may help search while slightly hurting the
  views — embed documents once, but consider prefix-free embeddings as the
  clustering input if the chosen model allows it. To be tested.
- Whether asymmetry helps *known-item* search of half-remembered own content
  is unestablished by any surviving source — open question, ours to answer.
- Reassurance for the zero-label setting: E5 beat BM25 on BEIR zero-shot with
  no labeled data (arXiv:2212.03533, priority adversarially confirmed against
  Contriever). Off-the-shelf encoders without fine-tuning are a defensible
  architecture for a single-user system.

## 2. Chunking: the largest lever

- **Anthropic contextual retrieval** (prepend an LLM-generated situating
  summary to each chunk): top-20 retrieval failures cut 35% by contextual
  embeddings alone, 49% with contextual BM25, 67% with a reranker. Medium
  confidence (single vendor, unreplicated, k=20 baseline failure was already
  5.7%). ytk already does a lightweight version of this — the video parts are
  prefixed with title+thesis — validating that design; the same treatment is
  the natural fix shape for #84 (memories).
- **Late chunking** (Jina, arXiv:2409.04701): ~2.7-3.6% relative nDCG@10 gain,
  largest at small chunks (our segment regime). But "training-free drop-in"
  was **refuted 0-3**, and follow-up work finds it not universally superior to
  contextual retrieval. A refinement, not a foundation.
- **No universal chunk size** (arXiv:2505.21700, arXiv:2603.06976): 64-128
  tokens win concise fact lookup; 512-1024 win broad-context questions; best
  strategy is domain-dependent; larger models do NOT rescue bad chunking.
  Implication: transcripts (timestamped fact lookup — keep small segments) and
  long notes/memories (broader) want different regimes, matched to query
  granularity. Caveat: no chunking study tested speech transcripts — the
  transcript inference is ours. Exact effect sizes for content-aware vs fixed
  chunking were refuted 0-3; direction survives, magnitudes don't.

## 3. Matryoshka: free where it matters, needed where we visualize

- MRL training is NOT required for moderate truncation: non-MRL models
  truncated to ~half dims are competitive or better. MRL clearly wins only
  under **heavy truncation (>=80% of dims removed)** — which is exactly the
  visualization regime (1024d -> 64-128d projection inputs).
  (arXiv:2605.16608, May 2026, unreplicated — medium confidence.)
- Most 2026-era models train MRL natively (Qwen3-Embedding, EmbeddingGemma,
  Jina-V5); older encoders don't. Choosing a 2026 encoder gets the
  low-dim-for-viz / full-dim-for-search split for free.
- Concrete curve (nomic-v1.5, vendor-reported): MTEB 62.28 @768d → 61.04
  @256d (-1.2) → 56.10 @64d (90% of full quality). So: full dims in Chroma
  for search; 64-128d MRL prefixes feeding UMAP/grove/galaxy at a fraction of
  the fit cost — architecture confirmed viable, exact loss on our corpus TBD.
- "MRL prefix truncation is suboptimal" (arXiv:2510.12474) went 1-2 — treat
  fancy alternatives to plain prefix truncation as unproven.

## 4-6. What the literature would not settle (now local experiments)

No claims survived verification on: multimodal text+image unification
(jina-clip, SigLIP-2 text-tower quality, projection bridges), zero-label eval
methodology (synthetic-query validity, known-item protocols, triplet/Procrustes
stability gates), or UMAP faithfulness vs embedding dim/isotropy. Silence, not
negative evidence — but it means the eval harness design (report 4) rests on
our own grove-experiment discipline rather than published protocol, and the
text/image split stays disjoint by default until we measure a reason to bridge.

## Refuted claims (do not cite these popularized versions)

1. Late chunking as a training-free generic drop-in — 0-3.
2. Chunk-size non-transferability across models (Stella vs Snowflake framing) — 0-3.
3. Paragraph-group chunking's large effect sizes (nDCG@5 0.459 vs <0.244) — 0-3.
4. "Static MRL truncation fails to preserve important dims" — 1-2.

## Sources

arXiv:2402.01613 (Nomic Embed) · arXiv:2309.07597 (C-Pack/BGE) ·
arXiv:2212.03533 (E5) · arXiv:2409.04701 (late chunking) ·
anthropic.com/news/contextual-retrieval · arXiv:2505.21700 (chunk size) ·
arXiv:2603.06976 (36 chunkers study) · arXiv:2605.16608 (MRL necessity) ·
huggingface.co/nomic-ai/nomic-embed-text-v1.5 + nomic.ai blog (MRL curve) ·
arXiv:2510.12474 (partially refuted).
