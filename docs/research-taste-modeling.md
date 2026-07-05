# Research: taste modeling for ytk

Date: 2026-07-05. Method: deep-research workflow — 5 search angles, 21 sources fetched,
105 claims extracted, top 25 adversarially verified (3 refutation votes each): 24 confirmed,
1 refuted. Feeds issues #12 (visual encoder), #16 (profile v2), #17 (prompt evals).

## 1. Visual embeddings (#12)

**Pick SigLIP-2, run it via mlx-embeddings.**

- SigLIP-2 extends contrastive image-text alignment with captioning-based pretraining,
  self-distillation, and masked prediction — the same self-supervised family as DINOv2.
  One encoder gives both CLIP-style text alignment and DINOv2-style dense features
  (arXiv:2502.14786). DINOv2 has no text tower; plain CLIP lags SigLIP on zero-shot
  retrieval. [3-0 verified]
- Local path on the M3: `mlx-embeddings` (Blaizzy) runs vision + text embedding models
  natively on Apple Silicon; documented checkpoint `mlx-community/siglip-so400m-patch14-384`
  (~1.76 GB, comfortable in 16 GB). SigLIP-2 support landed in v0.0.4. [3-0]
- DINOv2 also runs natively via `mlx-image` (small/base/large, patch14, 518px) — but
  mlx-image has no CLIP/SigLIP at all. Runtime choice determines model choice; the two
  candidates live in different runtimes. [3-0]
- Unresolved: no source benchmarked SigLIP-2 vs DINOv2 on social-save imagery (reel covers
  with text overlays, aesthetic pins, YT thumbnails). A ~100-pair local eval would settle it.
  DINOv2 wins instance-level retrieval benchmarks (DISC21: 64% vs CLIP 28%), SigLIP wins
  semantic/e-commerce retrieval (5 of 6 datasets) — our use case is semantic similarity,
  which favors SigLIP.
- Perf note: on Apple Silicon, image preprocessing (PIL decode/resize) can dominate
  end-to-end latency, not the model forward pass. Batch and cache accordingly.

## 2. Interest profiles (#16)

**Multiple interest embeddings, not one; thoughts are a separate channel with higher
confidence; no naive recency decay.**

- Single-user-embedding retrieval systematically over-represents dominant interests and
  starves torso/tail interests. Three independent production systems converged on multi-
  embedding profiles: Pinterest (KDD 2025, 7 implicit + 5 explicit embeddings, round-robin
  merge with dedup), MIND/Tmall (CIKM 2019), ComiRec/Alibaba (KDD 2020, K=4, per-interest
  retrieval then aggregate). [3-0 x4 merged]
  - Implication for ytk: retrieve per-theme and merge; never query with one profile centroid.
  - Magnitude caveat: the exact benchmark-margin claim was REFUTED (1-2); expect modest
    gains, direction is solid (REMI, RecSys 2023: wins depend on training details).
- Clustering saved-content embeddings into interest vectors is the validated construction:
  MIND explicitly frames its routing as soft K-means over behavior history. ytk's existing
  embedding-clustering approach is the right shape; per-cluster centroids become the
  multiple query vectors. [3-0]
- High-intent signals (save + written thought) get two treatments:
  1. **Separate retrieval channel** — Pinterest found explicit interests retrieve almost
     entirely different content than behavioral clusters (3.2% candidate overlap), most
     valuable for long-tail interests and low-activity users (a single-user corpus IS the
     low-activity regime). [3-0]
  2. **Higher confidence, not higher preference** — Hu/Koren/Volinsky (ICDM 2008):
     decompose implicit feedback into binary preference + confidence, c = 1 + alpha*r.
     For ytk: saved = liked (preference); an attached thought raises r, boosting the item's
     weight in centroids and profile ranking. alpha=40 is a dataset-specific constant —
     treat as a shape, not a number. [3-0 x4 merged]
- **Do not add exponential recency decay.** Yahoo Japan production eval (Okura et al.,
  KDD 2017, ~12M users): decay-weighted centroid AUC 0.596 vs plain centroid 0.608
  (non-overlapping CIs). Temporal dynamics only helped via a trained GRU (0.652) —
  untrainable for one user. If interest evolution matters, use discrete mechanisms:
  time-windowed profile snapshots, cluster birth/death across re-renders. [3-0 x3]

## 3. Prompt evals for the Haiku enrichment pipeline (#17)

Anthropic first-party guidance, verbatim-verified:

- **Code-graded first.** Programmatic assertions before any judge: schema validity, tag
  format, timestamp bounds, named entities actually present in the transcript. [3-0]
- **Volume over polish.** More lower-effort eval questions beat a tiny hand-polished set
  (variance reduction). Build the set from real past ytk ingests, matching the production
  difficulty distribution — include no-caption and short-video edge cases. [3-0]
- **LLM-as-judge, if used:** binary or 0-3 scales (judges can't hold a stable standard at
  1-10 — Databricks); judge from a different model family than Haiku (self-preference);
  randomize pairwise order (position bias); rubric scores content, not confident tone
  (authority bias); penalize length (verbosity bias). Validate the judge by reading graded
  samples. [3-0, judge-bias claims anchored on secondary source + primary corroboration]

## Open questions

1. SigLIP-2 vs DINOv2 on ytk's real corpus — needs a small local eval (~100 labeled pairs);
   do thumbnail text overlays pollute DINOv2's purely-visual neighborhoods?
2. Choosing K for a growing single-user corpus — nothing in the literature on adaptive K
   or cluster birth/death at hundreds-of-items scale.
3. Operationalizing confidence weighting in embedding space — is a save-with-thought r=3
   in a weighted centroid, duplicate-weight in clustering, or a seed for its own
   explicit-channel query vector?
4. Middle ground between plain centroids and per-user GRUs for interest evolution —
   time-windowed snapshots diffed across re-renders look most promising.

## Caveats

Scale transfer is the dominant uncertainty: all taste-modeling results come from web-scale
recommenders with engagement labels; applying them to one user's hundreds-to-thousands of
saves is reasoned extrapolation. No local benchmarks were run (mlx libraries verified via
docs/artifacts, not executed). The decay-hurts result rests on one verbatim-verified 2017
production paper.

## Key sources

- Pinterest multi-embedding retrieval (KDD 2025): https://arxiv.org/pdf/2506.23060
- ComiRec (KDD 2020): https://arxiv.org/pdf/2005.09347
- MIND (CIKM 2019): https://arxiv.org/pdf/1904.08030
- Hu/Koren/Volinsky implicit feedback (ICDM 2008): http://yifanhu.net/PUB/cf.pdf
- Okura et al., embedding-based news rec (KDD 2017): Yahoo Japan decay/GRU results
- SigLIP 2 (Feb 2025): https://arxiv.org/abs/2502.14786
- mlx-embeddings: https://github.com/Blaizzy/mlx-embeddings
- mlx-image: https://github.com/riccardomusmeci/mlx-image
- Anthropic eval guidance: https://github.com/anthropics/anthropic-cookbook/blob/main/misc/building_evals.ipynb
- LLM-judge biases: https://www.promptfoo.dev/docs/guides/llm-as-a-judge/ + arXiv:2306.05685
