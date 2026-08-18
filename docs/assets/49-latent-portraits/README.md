# 49 — Latent portraits (rung 7', part 2)

**Question.** GEN mode wanted to *imagine* what a latent looks like and
failed its gate. The extractive twin *composites* it: a latent's portrait is
the activation-weighted average of its exemplars' real thumbnails — every
pixel owned by the corpus, every contribution traceable to a note. No model,
no confabulation surface. The question is whether such portraits are
**identities** or just brown mush: does a latent's face survive being built
from a different half of its own evidence?

## Pre-registration (written before any measurement)

**Construction.** For each latent with **>= 12 image-bearing exemplars**
(top-24 activating docs/segments with resolvable thumbnails): center-crop
each thumbnail square, resize 128x128, average weighted by activation.
That image is the portrait. Disclosed limitation: portraits inherit
YouTube's design language (thumbnails are what channels chose, not what
latents mean) — they are evidence composited, not meaning rendered.

**Registered gate — identifiability (P1).** For each qualifying latent,
build two portraits from disjoint exemplar halves (even vs odd activation
ranks). Similarity = Pearson correlation over pixels. The same-latent
similarity distribution against the all-cross-pairs null must separate at
**ROC AUC >= 0.80**. Below the bar, portraits are decoration and the
section says so; at or above it, the wall and the hub may wear them.

**The passport (only if P1 passes).** One closing figure assembles the
protagonist's full papers: portrait, compass rose (section 48), SAE
fingerprint, named latents, atlas cell — every instrument the epic built,
on one page, for one note.

Numbers land in `portraits.json`; runner
`experiments/sae_qwen/latent_portraits.py`. Results follow below this line
only after the gate has run.
