# 53 — The patch grid (#218)

**Question.** Every use of the visual encoder in ytk keeps one pooled vector
per image and discards the 24 x 24 grid of patch tokens it was pooled from.
If that grid could be read, ytk could show which region of a thumbnail
answered a text query. Reading it is not free of traps: SigLIP-2 pools with
one learned probe attending over all 576 tokens, then a layernorm and an MLP,
so a raw patch token does not live in the text vector's space and a plain
patch-to-title cosine is a picture of nothing. Cheap maps also look
convincing whether or not they are faithful. So the cheap maps are gated
against a slow one that cannot lie: do the cheap per-patch maps agree with
occlusion?

## The lenses

All four read `google/siglip2-so400m-patch16-384` at the production revision,
fp16 on MPS for the vision tower, the pooling head copied to float32 on CPU.

1. **Where the probe looks.** The pooling head's attention weights over the
   576 tokens, averaged over heads. Free and text-independent: it shows what
   the encoder weighs whatever the query.
2. **Patch alone.** Each token pushed through the head as if it were the only
   one attended (value projection, output projection, layernorm, MLP with its
   residual), then cosine with the text vector.
3. **Cover a block.** The 384 x 384 input is cut into a 6 x 6 grid of 64 px
   blocks. One block at a time is set to zero in normalized pixel space
   (mid grey), the image is re-encoded, and the drop in image-text cosine is
   recorded. 37 forward passes per image. This is the referee: it uses only
   the model's real output.
4. **Gradient through the head.** The gradient of the image-text cosine with
   respect to each patch token, times the token, summed over the feature
   axis. One backward pass through the head only. It accounts for the probe's
   mixing and the MLP, which lens 2 ignores.

## Spike, before registration

Three thumbnails, used to check the plumbing and to look. They are excluded
from every sample below, so nothing seen in them can tune the gate.

- The pooled output reproduces the production embedding to cosine 1.0000.
- The occlusion maps are legible. In all three the hottest block sits on
  text in the thumbnail that the title names. True-title drops are 5 to 8
  times the wrong-title drops (0.013, 0.005, 0.025 against 0.002, 0.001,
  0.003).
- Lens 2 is speckled and nearly the same under the true and a wrong title
  (rank correlation 0.58 to 0.76 between the two).
- Lens 1 lands on a few scattered tokens in low-detail regions, not on the
  subject.
- Lens 4 was added because of what lens 2 looked like. Nothing is concluded
  from n = 3.

> **Later (same day, still before the gate, same three images):** the spike's
> readings were tested instead of trusted. What held: the occlusion map is
> not an artifact of the grey fill (rank correlation 0.81 to 0.94 against an
> image-mean fill), and it follows the question. Asked for an object in the
> picture and not the title, the hottest block moved off the printed text
> and onto the object in two of three images, partly in the third (rank
> correlation between the title map and the object map: 0.22, -0.64, 0.43).
> What was wrong: "low-detail regions". The ten most-attended tokens sit on
> patches with *more* pixel contrast than the rest (31 against 21, 34 against
> 20, 52 against 38). What they do have is length: before the final norm
> their vectors are about 510 long against about 67 for the other 566, and
> ten tokens of 576 hold 20 to 24 percent of the probe's attention. Covering
> the pixels under them, four or five of the ten stay the most-attended
> tokens anyway and the new top ten hold the same share, so the position
> matters more than what is under it. Covering them moved the pooled vector
> more than any of 20 random draws in two images and less than the random
> mean in the third. The guess that lens 2's speckle is these same tokens was
> not supported (rank correlation with the probe's attention 0.15, -0.11,
> -0.11); the speckle is unexplained. The interpretation bullet below that
> says "low-detail tokens" should be read as "long tokens".

> **Later (same day, before the gate, four non-YouTube images that cannot be
> in the sample):** the owner asked why the spike concluded the encoder
> looks for text, and what it does with no text. It was not a conclusion
> the spike could support: all three spike images were thumbnails whose
> titles repeat words printed on them, so printed words were the only thing
> there to find. On images with no printed words the referee lands on the
> named object: one block on the trackball for "a red trackball" (drop 0.051
> of 0.090), the goat's head and body for "a black goat", the one block
> holding the figure for "a small person". On an image with both, the
> printed caption and the woman each light under their own query. Two
> limits showed. Occlusion measures whether a block is *necessary*, not
> where a thing is: a subject that fills the frame loses almost nothing to
> any one block (largest drop 0.008 of 0.160 for the goat, 0.007 of 0.149
> for the keyboard, none at all for a face filling the frame), while a
> small, unique region carries 30 to 57 percent of the match. And the maps
> are min-max scaled per panel, so a drop of 0.002 renders as bright as one
> of 0.051; the number has to be read with the colour. For the gate this
> means the referee will be strong on thumbnails with printed words and
> weak on the rest, which the no-exclusions rule already commits to
> reporting and not repairing, and that the result will be about
> thumbnails with titles, not about images in general.

## Pre-registration (written before any gate measurement)

**Sample.** YouTube rows of the `ytk_visual` collection that carry a title
and whose image exists on disk, sorted by id, shuffled with
`random.Random(53)`. Positions 0 to 2 are the spike images. Positions 3 to
42 are the 40 gate images. The first 20 of those are also the rating images.
The query is the item's own title, embedded exactly as production does
(`visual.embed_texts`). The wrong title for image k is the title of image
k + 1 in the sample, cyclic.

**Statistic.** For each gate image and each cheap lens, the map under the
true title is reduced to the referee's 6 x 6 resolution (block mean for lens
1 and 2, block sum for lens 4, which is additive) and compared with the
occlusion drop map under the true title by Spearman rank correlation over the
36 blocks. The score of a lens is the mean of the 40 correlations.

**Registered gate.** A lens passes if both hold:

- **Mean rank correlation >= 0.40.**
- **It clears the null.** The null pairs each image's cheap map with the
  occlusion map of a *different* gate image. It measures what layout habits
  alone would score: titles burned into the lower third, a face on the
  right. 2,000 draws of 40 mismatched pairs give a distribution of null
  means; the observed mean must exceed its 95th percentile.

**Text-specificity, secondary.** For lens 2 and lens 4, the correlation of
the cheap map under the *wrong* title with the occlusion map under the true
title is computed per image. A lens reads the text if the paired difference
(true minus wrong) has a bootstrap 95 percent interval that excludes zero.
Lens 1 cannot pass this by construction and is reported for reference.

**No exclusions.** All 40 images are scored. The referee's own strength is
reported beside the result: the distribution of the maximum true-title drop
against the maximum wrong-title drop, per image. If the referee has no
signal on an image, that image lowers every lens's score, and that is
disclosed and not repaired.

**The owner's rating.** For the 20 rating images the owner sees lens 2,
lens 3 and lens 4 as overlays, unlabelled and in shuffled order per image,
with the title, and rates each hit, miss or can't tell: does the hot region
land on what the title names. A lens reads to the eye if its hit rate among
rated overlays is at least 0.60 with at least 10 rated. The rating is made
before the owner sees the gate's numbers.

**Interpretation, fixed in advance.**

- A cheap lens that passes the gate and reads to the eye can ship as a
  "why similar" overlay, computed at query time from cached tokens.
- A cheap lens that passes the gate and fails the eye, or the reverse, is
  reported as a disagreement between judges. The eye decides whether
  anything ships; the gate decides what is claimed.
- If both cheap lenses fail, only occlusion is faithful, at about 20 seconds
  per image and query. The section then records that the probe's mixing
  makes per-patch readings of this head unfaithful, and a feature would be
  on demand only.
- If lens 1's scattered low-detail tokens from the spike recur across the
  sample, that is recorded as an observation with a count, and its cause is
  left to a later section.

**Cost, measured in the spike.** 0.55 s per forward pass. The gate is 40
images x 37 passes, about 13.5 minutes of GPU on the M3. Lenses 1, 2 and 4
are seconds.

Numbers land in `patch_grid.json`; the runner is
`experiments/patch_grid/run.py`; figures come from
`scripts/plot_patch_grid.py`. Results follow below this line only after the
gate has run.

---

## Result (written 2026-09-23, after the gate and the blind rating)

**The gate failed, all three lenses.** Mean Spearman against the occlusion
referee over the 40 thumbnails: probe attention 0.02, patch alone 0.10,
gradient through the head 0.13, against the registered bar of 0.40. Two of
the three clear their layout null (patch alone 0.10 against a null 95th
percentile of 0.08; gradient 0.13 against 0.05), so they carry more than
thumbnail habit, but nowhere near enough to ship. Figure 01 draws each
observed mean inside its null.

**Only the gradient lens reads the query.** True title minus wrong title,
paired over the 40 images: gradient +0.09 with a bootstrap 95 percent
interval of [0.03, 0.15]; patch alone +0.06 with [-0.00, 0.13], which
touches zero. The registered rule calls the gradient lens text-reading and
patch-alone not. Figure 04.

**The owner rated all 60 blind overlays as misses.** Twenty images, three
lenses each, shuffled and unlabelled. Not one hit, not one "can't tell". The
reason was not the lenses: at the referee's 6 x 6 resolution every overlay is
36 grey blocks over a thumbnail, and nothing at that resolution lands "on"
anything. The rating measured the rendering, not the maps.

**The referee was weak on the material.** On 18 of the 40 thumbnails the
largest single-block drop was under 5 percent of the image-title match
(median 6.9 percent). A block that costs nothing cannot rank the others, so
half the sample scored every lens near zero whatever the lens did. The
no-exclusions rule commits to reporting that and not repairing it; figure 03
shows it.

**What the loss says.** More about the material and the resolution than
about the lenses. YouTube titles name nothing a block can be pointed at;
64-pixel blocks are too coarse to be read by eye or to give a small object
its own cell; and the referee only measures necessity, which a frame-filling
subject never concentrates in one block. The lenses may still be wrong, but
this section could not have shown them right.

**The pivot.** Section 53 closes here. The follow-up is one night of five
experiments on ten images with nameable objects and three hand-written
queries each, at the finest resolution each method allows, with the picture
first and any gate only after a picture has shown a claim worth defending.
The plan is `docs/design/patch-grid-night/README.md`; the sources it rests
on are in `docs/research/patch-grid-literature.md`. The per-image cache of
576 tokens and 37 covered embeddings for these 40 thumbnails stays under
`~/.ytk/patch_grid/` and is reused by section 55 for the long-token count.

Figures 01 to 05 and `scripts/plot_patch_grid.py` are committed as they were
rendered on 2026-09-20 from the gate run at `578f1b6`; they are the record of
what was measured, including the 6 x 6 overlays that could not be read.
