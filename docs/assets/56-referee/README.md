# 56 — A sturdier referee (#218)

**Question.** Every cheap map in this record is judged against occlusion:
cover part of the image, re-encode, see what the match loses. Section 53's
referee was a 6 x 6 block cover, too coarse to read and blind to a subject
that fills the frame, because covering any one block of it costs nothing.
Two sturdier referees were proposed: cover each whole SAM object in turn
(necessity at object resolution), and RISE (arXiv 1806.07421), which covers
random multi-region masks and asks what the match expects when a patch is
kept. Do they rank regions the same way as each other and as the sliding
cover? If yes, the cheap covers are enough and RISE is never needed again.

Section 3 of the patch-grid night, `docs/design/patch-grid-night/README.md`.

## What was done

- **Whole-object occlusion.** For every region of every one of the ten
  images (28 to 110 per image, 553 in all): grey the region's pixels, encode,
  keep the pooled vector. Text-independent, so any query is one dot product
  later. 5 min on the M3. `run56.py objects`.
- **RISE.** On three images (the woman, the goat as the frame-filling case,
  the sewing cabinet as a new small-object case): 2,000 random 7 x 7 binary
  grids at p = 0.5, bilinearly upsampled with a random sub-cell shift to
  24 x 24 and then to 384 x 384, multiplied into the normalised pixels (zero
  is mid grey, as in section 53). Pooled vectors kept per mask. The map is
  the mean match over masks that keep the patch, minus its mean over
  patches. 53 min for three images, about 18 min each, against the plan's
  11: the spike's per-pass figure did not hold at batch 16 on masked inputs.
  `run56.py rise`, in a tmux window.
- **Comparison.** Whole-object drops are put on the 24 x 24 grid by giving
  each patch the largest drop of any region that owns it; Spearman with the
  RISE map over the 576 patches. Winners: the region whose cover cost most;
  for RISE, the region with the highest mean saliency per patch.

## Result

**The three referees do not agree, and the dead end did not fire.**

- **Whole-object against RISE**, Spearman over 576 patches: -0.28 on the
  woman ("a woman wearing sunglasses"), +0.08 on the goat ("a black goat"),
  +0.53 on the sewing cabinet ("a white sewing machine"). Nowhere near the
  0.7 the plan set as "the cheap covers are enough". Figure 01.
- **RISE lights the goat.** Figure 03: at 200 masks the goat's body is
  already the hot region, at 500 the map's rank order is 0.93 with the
  2,000-mask map, at 1,000 it is 0.97. On the frame-filling subject that the
  6 x 6 cover could not see in section 53, RISE says the goat, cleanly, and
  1,000 masks would have done. Whole-object occlusion also says the goat
  (largest drop 0.035 of 0.152, 23 percent of the match); the two agree on
  the winner and disagree everywhere else, which is what a rho of 0.08 on
  576 patches means: RISE draws a smooth hill around the goat and the
  object cover paints one region and leaves the rest at zero.
- **RISE finds the subject; whole-object occlusion misses the woman.** For
  "a woman wearing sunglasses" RISE's hill sits on her head and its top
  region is the sunglasses; the sliding cover puts the loss on her head
  too. The region whose whole cover cost most is a block of buildings
  behind her (9.6 percent of the frame, drop 0.010 of 0.131); her face,
  which both section 54 recipes chose, costs 0.006. On the sewing cabinet
  RISE's hill sits on the machine and the wall above it; the object cover
  says the floor. RISE's values are small in absolute terms (a range of
  0.005 around the mean match on the woman) because they are expected
  scores under half-covered images, not drops, which is why figure 01 gives
  the column its own scale; the shape is sharp. Two of three times, the
  referee the plan called the cheap one is the one that is wrong.
- **Whole-object occlusion prefers big regions.** Figure 02, the
  small-object question on all ten: it agrees with crop-on-grey's winner on
  3 of 10 (goat, owl's mouse, selfie's sunglasses). In 6 of the 7
  disagreements its winner is the larger region: a keyboard half instead of
  the trackball, the anime woman instead of the rose, the sewing room's
  floor instead of the machine, the keyboard photo's whole background
  instead of the cable. Covering more pixels costs more match whatever they
  show. On the frame-filling question it agrees on 4 of 9. This is
  section 53's "occlusion measures necessity" limit at object resolution:
  necessity scales with area.
- **Drop sizes.** The largest single-object drop is 6 to 78 percent of the
  match (median 19 percent on the small-object question). Four of the ten
  small-object queries lose under 0.015 of cosine to their best cover, the
  same range as covering a random region.

**Reading.** RISE is the referee that reads right on all three images, and
it costs 18 minutes an image on this machine at 2,000 masks, about 9 at the
1,000 figure 03 shows is enough. Whole-object occlusion is fast,
text-independent and cacheable, and it is biased toward area, so it cannot
be the referee for small things on its own. The honest use for section 58 is
both: agreement with the object cover on all ten, with RISE on the three,
and the disagreements read as disagreements. The plan's "if they agree above 0.7 on
all three, RISE is not needed again" has the answer no, and the useful
negative is the other one: covering whole objects is not a referee for
small things.

## Figures

- `01-three-referees.png` — the woman, the goat and the sewing cabinet: the
  sliding cover (woman only), every whole object covered, RISE; the region
  each ranks first in gold; Spearman in the corner.
- `02-every-object-covered.png` — all ten images, the small-object question,
  whole-object occlusion beside section 54's crop-on-grey vote.
- `03-does-rise-converge.png` — the goat's RISE map at 200, 500, 1,000 and
  2,000 masks on one scale.

Caches `~/.ytk/patch_grid/night/56_*.npz`; runner
`experiments/patch_grid/run56.py`; figures `scripts/plot_night.py 56`.
