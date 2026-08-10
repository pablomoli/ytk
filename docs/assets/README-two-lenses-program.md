# The two-lenses program (assets 22-25) — reconciled ledger

One question, four experiments, 2026-08-07/08: **the profile is built in one
embedding space; would a second space see a different person, and can the two
be combined?**

Every number below was re-read from the artifacts on disk and cross-checked
across sections on 2026-08-09; asset 22's battery was independently re-run and
reproduced to the 4th decimal. Where sections disagree, the later one wins and
the earlier is annotated in place.

| asset | experiment | script | verdict |
|---|---|---|---|
| 22 | two lenses: Qwen themes vs gemma-2-2b SAE clusters | `plot_two_lenses.py` | they measure different things: topic vs voice |
| 23 | E1 — StyleDistance as the voice lens | `e1_style_lens.py` | better voice meter, different partition |
| 24 | E2 — native SAE trained on the Qwen space | `plot_native_sae.py` + `experiments/sae_qwen/` | annotation layer yes, replacement no |
| 25 | E3 — shared/private CCA decomposition | `e3_shared_private.py` | the lenses agree on topic; no derivation available |

Universe throughout: **532 notes** — the intersection of the frozen 568-note
fingerprint batch (2026-08-02) with the 604 themed notes of the 2026-08-08
snapshot, matched by exact `note_texts()` keying and sha-verified 562/563.
Every partition uses production `choose_k` and seeded KMeans, so the space is
the only variable.

## The reconciled numbers

Source purity — what a partition actually sorts by (Instagram vs YouTube/web;
majority baseline **0.605**):

| lens | purity | reads |
|---|---|---|
| Qwen production themes | 0.718 | subject matter |
| gemma-2-2b SAE clusters | 0.949 | register / medium |
| StyleDistance | 0.959 | register, with less topic bleed |
| Qwen-private (shared removed) | 0.639 | nothing new — equals a plain re-cluster |

Agreement, always against its null and its ceiling:

| pair | ARI | context |
|---|---|---|
| SAE vs themes | 0.239 | ceiling 0.335, null 0.000 |
| StyleDistance vs themes | 0.035 | near-zero topic contamination |
| StyleDistance vs SAE | 0.114 | the two voice lenses are *not* the same partition |
| within YouTube (n=287) | 0.047 | their agreement was mostly medium |

Geometry (triplet, chance 0.500): SAE vs Qwen **0.644**, StyleDistance vs SAE
**0.682**, StyleDistance vs Qwen **0.548**. Geometries agree far more than
partitions do — this corpus is gradients, not clusters.

## What each experiment closed and opened

**22 — the founding split.** Two spaces, two different people: Qwen sorts by
what a note is *about*, the SAE rig by how it *sounds*. Gave the earlier 19.1
retrieval failure its mechanism — a space organized by voice cannot find
topical neighbours across media. *Opened:* is register real, or just the
`source` field restated? *Side finding:* the profile eval carries a **~0.19
noise floor** (13 runs, one frozen cohort, nDCG 0.517-0.737; four runs on an
identical 280-note corpus spread 0.191). Clustering is seeded, so the Claude
claim-writing call is the only varying stage.

**23 (E1) — register is real, but the lenses disagree about it.** StyleDistance
matches the rig's purity at 20x fewer parameters and 150 s for the whole
corpus, with essentially no topic bleed, and resolves within-YouTube voice
structure 2.5x more crisply (silhouette 0.108 vs 0.043, null -0.005).
*Closed:* the "voice is just the medium" worry — structure survives inside one
medium. *Opened:* once medium is removed the two voice lenses barely agree
(ARI 0.047, triplet 0.562), so at least one is not measuring voice. Unresolved.
*Caveat:* pooling choice dominates the flat partition (ARI 0.18-0.49 across
three poolings), so the conclusions rest on silhouette and triplet, which do
not depend on it.

**24 (E2) — the production space can name itself, but cannot be indexed by its
own code.** A top-k SAE (dict 2048, k=32, held-out recon cosine 0.829 +/-
0.008) reads *subject matter* far finer than the 17 themes, and the
frequently-firing head of the dictionary survives independent retraining
(top-100 mean max-cos 0.762, 50% above 0.8, vs 6.5% for the full dictionary;
random null 0.107). *Closed:* replacement — reconstruction fails the retrieval
gate at every config (overlap@10 0.73-0.79, hit@5 -0.026 to -0.081 against a
0.02 tolerance), and the numpy mirror reproduces the frozen baseline exactly,
so the loss belongs to the bottleneck. Also closed: cosine-only sweeps, which
rank configs differently from faithfulness. *Opened:* a read-only annotation
layer over the reproducible head.

**The program-level catch:** the deliberate-save signal is a **disguised medium
label** — every r>=1 note is Instagram/TikTok/web, every r=0 note but seven is
YouTube. The confounded target is trivially linear in raw vectors (AUC 0.978);
holding medium fixed yields nothing sign-stable at 27 positives. Any pipeline
weighting by r-levels is partly weighting by medium, **the profile's alpha=7
signal weighting included**.

**25 (E3) — the derivation is impossible, and the reason is the finding.**
Regularized CCA finds a large, genuine shared subspace: 25/25 held-out
canonical correlations beat a 200-permutation null by a wide margin (dim 1
r=0.961; best permutation ever 0.220), stable across PCA widths 30/50/100.
Those 25 directions carry **33.8%** of Qwen's variance against **36.6%** for
its own top-25 principal subspace. *Closed:* shared/private as a route to a
de-biased topic axis — stripping the shared subspace leaves purity at 0.639
(exactly a plain re-cluster) while a random-direction control sits *higher* at
0.677, and topical agreement collapses 0.327 -> 0.021 as the control holds
~0.37. There is no clean topic axis under the voice **because topic is what
the two lenses agree on**; their disagreement lives in low-variance private
tails a flat partition cannot reach. SPLICE is not worth building here.

## Two corrections to the earlier record

1. **E2's prediction, which E3 was sent to test, is refuted.** Shared structure
   is topical, not medium: mean excess eta-squared 0.254 (theme) vs 0.054
   (medium) over 25 dims; only 2/25 medium-dominant; removing all 25 leaves SAE
   purity at 0.951. The true part is narrower — a medium axis exists and is
   strong (within-medium stratified null 0.773 vs 0.961 observed) but it is
   dimension 5, and it turns out to be *document furniture* (headers, blank
   sections, punctuation, dashes). Dimension 1 is a software-engineering vs
   natural-science axis, read off the *voice* lens.
2. **The "measured ceiling" is soft.** Removing 25 *random* directions from the
   1024-d space lands ARI-vs-themes anywhere in **0.31-0.48**, so asset 22's
   0.335 is one draw from a wide band. Readings of the form "0.239 is 71% of
   ceiling" are retracted; the direction of the gap stands, the ratio does not.

## Doors now open

- **Annotation layer** (E2's head of dictionary) over production vectors —
  the only architecture all four experiments agree on.
- **Voice as a held-constant control** (StyleDistance, 150 s/corpus) for feed
  diversification or topic-net-of-style retrieval — not as a profile facet.
- **Fixing the r-label confound** — a prerequisite for any taste experiment,
  and an open question about the profile's own alpha weighting.
- **E4 (facet profile) needs redesign.** It assumed theme x voice was a
  meaningful cross; E3 shows the axes overlap heavily on topic and E1 shows
  the voice lenses disagree once medium is removed. The honest version is
  themes annotated with named SAE *topic* features, not a topic x voice grid.

## Doors now closed

- Replacing the production encoder or index with any sparse/derived code.
- Shared/private decomposition (linear or SPLICE) on a corpus this size.
- Reading single-run profile-score deltas as signal (~0.19 noise floor).
- Treating the 0.335 ARI ceiling as a fixed bar.
- Benchmarking gemma-2-2b as an embedder, or bge-small as a rival (already
  rejected on geometry in the encoder audit).

## Standing caveats

Fingerprints frozen at 568 notes; the corpus-wide rebatch failed twice
(wedged MPS process after machine sleep) and `sae_batch.py` is now
checkpointed and resumable, verified bit-identical across an interrupted run
— rerunning it retires the 532/604 coverage limit. Neuronpedia auto-names are
unprobed hypotheses throughout (the 18.x drug-usage lesson). KMeans on this
corpus moves ~0.1 ARI under trivial perturbation, so differences below that
are not read as real.
