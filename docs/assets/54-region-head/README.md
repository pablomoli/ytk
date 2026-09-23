# 54 — The region-masked head (#218)

**Question.** TextRegion (arXiv 2505.23769) locates a text match in SigLIP-2
without bypassing the pooling head: one encoder pass, then the real head run
once per SAM region with the attention logits set to minus infinity outside
that region's patches. One vector per region, in the text tower's space,
from tokens ytk could cache at save time. Does it pick the same region as
the spike's crop-on-grey recipe, and where they differ, which one does
covering the region and re-encoding side with?

Section 1 of the patch-grid night, `docs/design/patch-grid-night/README.md`.

## The ten images

Fixed for every section of the night. The four spike images plus six drawn
from `ytk_visual` by the plan's rule (instagram or pinterest, no thumbnail,
`random.Random(54)` over 71 candidates in id order, the first six holding two
nameable objects and at most one line of printed text; positions 0, 3, 10,
13, 31, 41 passed, the rest were text carousels, infographics and book
covers). Names, paths and queries live in `experiments/patch_grid/night.py`
and `queries.json`; figure 00 is the reference sheet.

| name | id | small object | fills the frame | absent |
|---|---|---|---|---|
| goat | ig:DH7a_cmuzlqA6O7uVAxnX3b5A3zovuZnFPSo_s0 | a black goat | dry grass and sandy ground | a red bicycle |
| keyboard-render | pin:306174474692151881 | a red trackball | a split ergonomic keyboard | a coffee mug |
| skull-moon | ig:DatQD1jjpJ- | a small person standing alone | a giant skull-faced moon with huge black eyes | a sailing boat |
| woman-river | ig:DcGVYrukZ6g | sunglasses | a woman wearing sunglasses | a dog |
| keyboard-photo | pin:306174474692067382 | a coiled black cable | a split mechanical keyboard with white keycaps | a cat |
| anime-window | ig:DbEzhk1DhUl | a red rose | a woman in a brown dress | a bicycle |
| sewing-cabinet | ig:DaATV4rlCC2 | a white sewing machine | a dark red cabinet | a television |
| barn-owl | ig:Da5KllRjZRu | a mouse holding a sword | a barn owl | a car |
| sunglasses-selfie | ig:DaICTFUAeI_ | sunglasses | a white long-sleeve shirt | a tree |
| kasai-art | pin:422281212512353 | red blood vessels | white flower petals on a blue sky | a human face |

Ruling at setup: the KASAI art has no small unique object, so its small
query names its thinnest structure. The owner may swap any image by editing
`queries.json`; every later section reads the same file.

## What was done

- **Regions.** `facebook/sam-vit-base` automatic masks with the spike's
  settings (pred_iou 0.80, stability 0.85, area 0.15 to 85 percent of the
  frame), largest first. 28 to 110 per image; the woman image reproduced the
  spike's 46. Each pixel mask maps to the 24 x 24 patch grid after the
  processor's squash to 384 x 384: a patch belongs to a region if at least
  half of it is covered. 45 of 553 regions were too small to own a patch
  that way and were given their single best-covered patch (ruling; the plan
  said half coverage and nothing about the remainder).
- **The head.** `experiments/patch_grid/region_head.py::region_vectors`, a
  pure function over cached tokens and boolean grids: the production head's
  probe, attention, layernorm and residual MLP, with a float mask of minus
  infinity on the logits outside the region, one row per region in a single
  batched call. `tests/test_region_head.py` checks that a full mask
  reproduces the production embedding to cosine above 0.9999 and that a
  half mask does not. It passed.
- **Crop-on-grey.** The spike's method, re-run on all ten: keep one region,
  grey the rest, crop to its box with 12 px of padding, encode. One encoder
  pass per region, about 30 s per image including SAM.
- **Scoring.** Regions compete by softmax(cosine x logit_scale) over the
  regions of one image, logit_scale 110; brightness in the figures is a
  region's share of that vote relative to the winner. A query whose
  whole-image cosine is at or under the highest any of the ten absent
  queries reached (0.047, the KASAI art against "a human face") is treated
  as unanswered by the picture and gets no map. That rule (the plan's
  "never draw a map for a query whose whole-image match is near zero", with
  the threshold taken from the absent controls rather than chosen) also
  removed two real things: the goat's "dry grass and sandy ground" (0.046)
  and the woman's "a stone wall" (0.031). It is disclosed on the panels.
- **The tiebreaker.** Where the two methods pick different winners, each
  candidate region is greyed in pixel space and the image re-encoded; the
  larger drop in whole-image cosine is the region the model needed more.
  Two passes per disagreement.
- Run order: the woman stage (spike masks and caches, CPU head only) ran
  first; the ten-image crop pass ran in the background while the woman
  figure was being drawn, so the first picture was seen before any result
  from the rest was read but not before it was computed. Ruling, recorded.

## Result

**Dead end, by the plan's own condition: the masked head picks the right
region less often than crop-on-grey.**

- 19 of the 30 queries are answered by their picture under the absent-query
  rule; all 10 absent controls fall below it, as they should, and none is
  drawn.
- On those 19, crop-on-grey and the masked head pick the **same winner on
  11**, and in every one of those the winner is the named object: the
  goat, the trackball, the small figure and the moon, the woman's face,
  the coiled cable, the rose, the sewing machine and the cabinet's side, the
  mouse and the owl. Both recipes work when they agree, and figure 02 shows
  what the agreement looks like at pixel resolution.
- On the **8 disagreements** the covering tiebreaker sides with
  **crop-on-grey 6 to 2**. The head's two wins are the keyboard photo's
  background (68 percent of the frame, whose cover cost 0.022 against 0.007
  for the crop's keycap cluster, a case where necessity favours whatever is
  large) and a coin flip on the KASAI art (0.005 against 0.004). Its six
  losses have one shape: a region of the wrong size. For frame-filling
  queries it picks the background (the render's desk, 402 patches) or a
  sliver (the selfie's shirt query lands on 11 patches, the anime dress on a
  48-patch line, the KASAI petals on 11 patches); for "sunglasses" it picks
  a single patch on the woman and an 83-patch strip of wall on the selfie.
  Covering those cost the match nothing (drops of -0.002 to +0.008), while
  covering the crop's picks cost 0.014 to 0.039.
- On the woman image with the spike's six queries the two recipes differed
  on four of six, agreeing only on the face for "a woman wearing sunglasses"
  and on the crop's method being sharper for the caption: the sliding cover
  puts the printed caption's drop at 0.054 of 0.182 exactly on the text,
  which no SAM region covers, so both recipes choose a neighbour (the shirt,
  the wall). Figure 01.
- **The mechanism.** Figure 04: confined to a region, the probe puts a
  median 47 percent of its attention on one patch (range 14 to 100), so a
  region's vector is largely one or two tokens' worth of value, whichever
  the probe already liked. Unconfined, the top patch takes 5 percent and the
  top ten 25 percent, the long-token pattern from section 53. The cached
  tokens sit after the encoder's final layernorm (norms 38 to 42, none above
  150), so whether the head's bad picks are the regions holding long tokens
  cannot be read from this cache; section 55 hooks the layers where the
  norms are measured and can revisit it.

**Reading.** Masking the head is faithful to the model (the full mask is the
production vector) but not to the object: the head was trained to pool a
whole image, and given a strip of wall or a desk it still produces a
confident vector, one that the text "a split ergonomic keyboard" matches
better than the keyboard's own region does. Crop-on-grey pays 46 encoder
passes to make the encoder look at the object alone, and on this material
that is what buys the right answer. TextRegion's gains were measured on
segmentation benchmarks with SAM2 masks and a tuned recipe; on ten photos
with sam-vit-base masks and no tuning, the plain masked head loses.

## For ytk

`region_vectors(head, tokens, grids)` is in `experiments/patch_grid/`, not
in `ytk/`. If it were used: storage per image is R x 1152 fp16, about 106 KB
for 46 regions, and a query is one matmul over the stored rows. On this
result it should not be, unless section 55 shows that hiding the long tokens
fixes the wrong-size picks. Crop-on-grey costs about 25 s of encoder time
per image at save time and the same 106 KB; it is the recipe that works.

## Figures

- `00-the-ten.png` — the reference sheet: ten images, every SAM region
  painted and outlined, three queries each, the absent one in red.
- `01-the-woman-three-ways.png` — the woman image, one row per spike query:
  picture, crop-on-grey, masked head, sliding occlusion; the winner outlined
  in gold on its real pixel mask; unanswered rows say so.
- `02-all-ten-all-thirty.png` — all ten images, all thirty queries, crop
  beside head for each. Ruling: one row per image with the three queries as
  column pairs rather than one row per image-query pair, because thirty rows
  at legible cell size would be a 20,000-pixel PNG; all thirty pairs are
  shown.
- `03-where-they-disagree.png` — the eight disagreements, crop's winner in
  blue, the head's in gold, each painted with the drop its cover cost.
- `04-attention-inside-each-region.png` — the probe's attention unconfined
  and confined to each of the woman image's 46 regions.

Numbers and caches: `~/.ytk/patch_grid/night/54_*.npz`; runner
`experiments/patch_grid/run54.py`; figures `scripts/plot_night.py 54`.
