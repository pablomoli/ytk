# The patch-grid night: one session, five experiments, in order

Status: plan. Nothing here runs until the owner says go. Written 2026-09-21
from the state of `exp/53-patch-grid` at `4bf38ac` and the literature brief
in `docs/research/patch-grid-literature.md`. The session that executes this
is a fresh one, started in the worktree, and it reads this file first.

## What the night is for

Three goals, in the owner's order, set on 2026-09-20 after section 53's gate
failed and its blind rating came back all misses:

1. See what the encoder sees, in pictures readable without a legend, on
   images and questions where there is something to point at.
2. A "show me where" view for ytk: given a query and a saved image, light the
   region that answered. Work at save time, one multiplication at query time.
   Judged by the owner's eye.
3. Figures and write-ups worth publishing, in the record's house style.

The rule that governs every experiment below, learned the hard way that
same night: **the first deliverable of each experiment is one picture at the
finest resolution the method allows, on material with something to point
at.** Gates, nulls and ratings come only after a picture has shown a claim
worth defending. No 6 x 6 grids. No blind-rating pages.

## What the session inherits

| Thing | Where | State |
|---|---|---|
| Branch and worktree | `exp/53-patch-grid` at `~/Developer/ytk.exp-53-patch-grid` | 8 commits ahead of master; its own `.venv` has torch 2.11, scipy, transformers 5.5.4 |
| Section 53 | `docs/assets/53-patch-grid/` | README with pre-registration and two Later notes; `patch_grid.json` (the failed gate); five rendered figures and `scripts/plot_patch_grid.py` UNCOMMITTED; no result section written |
| Gate cache | `~/.ytk/patch_grid/*.npz`, 40 images, 55 MB | per image: `tokens` (576 x 1152, the last hidden state), `covered` (37 pooled embeddings, one per 6 x 6 occlusion), the four lens maps, `base` |
| Spike caches | `/tmp/ytk-checkpoints/*.npz` | `slide.npz` (441-position sliding occlusion on the woman-by-the-river image, 4 queries), `sam_masks.npz` (46 SAM masks, same image), `sam_scores.npz`, `seg.npz`, `notext.npz`, `spike.npz`, `validate.npz`. `/tmp` survives a reboot on this machine only until cleared; copy anything needed into `~/.ytk/patch_grid/` first |
| Throwaway scripts | `/tmp/ytk-checkpoints/*.py` | the sliding cover, the SAM cut, the SAM score, and their plots; reusable as starting points, never committed as they are |
| Models on disk | HF cache | `siglip2-so400m-patch16-384` at the pinned revision; `facebook/sam-vit-base` |
| Literature | `docs/research/patch-grid-literature.md` | verified sources; the five ranked experiments this plan follows |

Measured costs on the M3, fp16 on MPS: SigLIP-2 forward 0.55 s per image;
sliding occlusion 2.5 min per image; SAM automatic masks 17 s per image (46
kept); one SAM crop scored by SigLIP about 0.3 s. Model load 12 s.

## Figures: the owner's standing order

Stated by the owner on 2026-09-21, and it overrides any shortcut below.

- **A figure at every stage.** Not one per section: every step that
  produces data produces a figure of that data, sent to the owner as it
  lands. Setup produces a figure (the ten images with their masks and
  queries). A dead end produces a figure (the picture that shows why).
- **In the design system.** Every figure imports `scripts/plot_assets.py`
  and follows `docs/assets/README.md`: the header block, the meta line
  carrying the measured quantities, `verdict()` where there is a verdict,
  `frame_panels`, DIM reserved for nulls, one claim per figure. A
  checkpoint wears the same style as an asset.
- **The representation must fit the data.** A figure is a picture of the
  thing measured, in the geometry the thing has, never a generic chart of
  numbers about it. Concretely:
  - A map over an image is drawn on the image, at the resolution the method
    produced it (24 x 24 patches, pixel masks, 441 sliding positions), with
    the real outline of the winning region, never downsampled to blocks.
  - Anything measured per layer is drawn along depth, all 27 layers as a
    row, one line per image, so the shape of emergence is the finding.
  - Anything measured per patch position is drawn on the 24 x 24 grid.
  - A comparison between two methods is the two maps side by side on the
    same image under one colour scale, with the disagreement drawn, not a
    correlation coefficient in a caption. The coefficient goes in the meta
    line.
  - A distribution over images is drawn as the distribution, with the
    individual images as marks, and the null in DIM when there is one.
  - Bar charts of summary numbers, unlabelled scatter plots, and any panel
    that would look the same for a different experiment are not acceptable.
    If a figure could have been drawn without the images, it is the wrong
    figure.
- **Data rich.** Fill the panels. A row per image, a column per query or
  method; the ten images and their queries are all shown, not a chosen
  example plus a number for the rest. Where the row count makes a figure
  tall, it is tall.
- **All of them delivered.** Every figure rendered during the night is sent
  to the owner with SendUserFile at the moment it is rendered, checkpoint or
  asset, kept or superseded. Every asset figure is committed in its section
  folder. Nothing is summarized in prose that could be shown.

## Ground rules for the executing session

- Start in the worktree. `cd ~/Developer/ytk.exp-53-patch-grid`. Every run is
  `HF_HUB_OFFLINE=1 uv run python ...`; SAM also needs `--with torchvision`.
  The offline flag is not optional: the processor load hit the hub and failed
  with a 401 once in three runs without it.
- Before the first GPU run: `curl -s localhost:6969/api/ingest/status` must
  show `"running":false`, and `memory_pressure` must be above 30 percent
  free. Never kickstart, restart or kill the hub. Never `pkill`.
- Anything over five minutes of GPU runs in a visible tmux window in the
  `ytk` session, named for the experiment, so the owner can watch it. List
  panes by name right before `send-keys`.
- Checkpoint figures go to `/tmp/ytk-checkpoints/` and are sent to the owner
  with SendUserFile as they land, not batched. Section figures go to
  `docs/assets/NN-*/` and are committed.
- Every figure imports `scripts/plot_assets.py`. Read
  `docs/assets/README.md` before the first figure. Maps that share a
  question share one colour scale; the meta line says what the scale is.
  Never draw a map for a query whose whole-image match is near zero: say so
  in the panel instead.
- Commit on the branch after each experiment, narrative in the commit
  message, and comment the outcome on #218. No merge. No reinstall. The
  branch is presented at the end for the owner's review.
- Each experiment has a dead-end condition from the brief. When it fires,
  write the section as a loss, commit, and move to the next experiment.
  Do not tune past a dead end.
- Sequential. One experiment at a time, finished and committed before the
  next starts. If the session runs out of context, the handoff is this file
  plus the commit log; each section README records exactly where it stopped.

## Images

The gate's 40 YouTube thumbnails stay available (their tokens are cached)
but they are the wrong material for pictures: titles name nothing you can
point at. The night uses a fixed set of ten, chosen by rule so no one has to
be asked at 3 a.m.:

- The four non-YouTube images already used in the spikes (goat, split
  keyboard, skull moon, woman by the river), because their spike results are
  the baseline every method is compared against.
- Six more from `ytk_visual` where `source` is `instagram` or `pinterest`,
  `image_path` does not contain `thumb`, chosen as the first six in
  id order after `random.Random(54).shuffle` that a quick look confirms hold
  at least two nameable objects and no more than one line of printed text.
  Record the ids in the first section README so every later section uses
  the same ten.

Each image gets three hand-written queries at setup, recorded in a
`queries.json` next to the section: one object that is small and unique,
one that fills much of the frame, one that is absent. The absent query is
the control every map has to fail visibly, and it is always drawn last in
the row.

The owner may replace any of the ten, and may add sparring frames, by
editing that file before saying go. No sparring footage is in the vault
today, so the plan does not assume any.

## The sequence

Each experiment becomes its own numbered section of the record, with the
usual README (question, what was done, result, figures) and its row in
`docs/experiments.md`. Section 53 is closed first.

### 0. Close section 53 honestly (30 minutes, no GPU)

- Write the result below the line in `docs/assets/53-patch-grid/README.md`:
  the gate failed (mean Spearman 0.02, 0.10, 0.13 against 0.40; lens 4
  reads the query, interval [0.03, 0.15]; lens 2 does not), the owner rated
  all 60 blind overlays as misses because 6 x 6 blocks are illegible, and the
  referee had under 5 percent signal on 18 of 40 images, so the loss says
  more about the material and the resolution than about the lenses. State
  the pivot and point at this plan and the literature brief.
- Commit `scripts/plot_patch_grid.py` and the five figures as they are: they
  are the record of what was measured. Add the row to `docs/experiments.md`
  with the public one-liner.
- Copy `/tmp/ytk-checkpoints/*.npz` into `~/.ytk/patch_grid/spikes/`.
- **Figures.** One: the ten images in a row, each with its SAM masks drawn
  as coloured regions and its three queries printed beneath, the absent
  query marked. It is the reference sheet for every later figure.

### 1. Section 54: the region-masked head (TextRegion) — about 1 hour

The brief's top-ranked experiment, resting on arXiv 2505.23769.

- **Setup.** For each of the ten images: one SigLIP-2 pass, keep the 576
  tokens; SAM automatic masks with the settings that produced 46 objects
  (pred_iou 0.80, stability 0.85, keep area between 0.0015 and 0.85 of the
  frame); map each pixel mask to the 24 x 24 patch grid by coverage, a patch
  belongs to a region if at least half of it is covered. About 20 s per
  image, all ten in a tmux window.
- **The method.** Run the real pooling head once per region with the
  attention logits set to minus infinity outside the region's patches. The
  head is `vision_model.head`; the masking goes into
  `head.attention(probe, h, h, attn_mask=...)`. One region vector per mask,
  same space as the text tower. This is the piece of code the whole night
  turns on; it is about fifteen lines and is written first, as a pure
  function over cached tokens and a boolean mask, with a unit test that a
  full mask reproduces the production embedding to cosine 0.9999.
- **The picture.** For the woman-by-the-river image, one row per query:
  the picture, crop-on-grey (the spike's method, from `sam_scores.npz`), the
  masked head, and the sliding occlusion from `slide.npz`. Objects compete
  by softmax(cosine x logit_scale); brightness is share of the vote relative
  to the winner; the winner gets the gold outline. Send it before anything
  else is run.
- **Then all ten.** A contact sheet, one row per image, best region per
  query under both methods, the absent query included.
- **Readout, no gate.** For each image and query, does the masked head pick
  the same winning region as crop-on-grey; where they differ, which one the
  occlusion map from the spike sides with. A count, in the README, and
  the owner's eye on the sheet in the morning.
- **Dead end.** Masked-pool picks the right region less often than
  crop-on-grey on the ten, or every region containing a long token scores
  alike.
- **Figures, in order.** (1) The woman image, one row per query, four
  columns: picture, crop-on-grey, masked head, sliding occlusion; the
  winning region outlined in gold on the real pixel mask; one colour scale
  per row. (2) The same for all ten images and all thirty queries, one row
  per image-query pair, a tall figure. (3) The disagreement figure: only the
  pairs where the two methods pick different winners, both outlines drawn on
  the image in two colours, with the occlusion map beside them as the
  tiebreaker. (4) A 24 x 24 grid showing, for one image, the probe's
  attention inside each region under the mask, so the mechanism is visible
  and not only its output.
- **Deliverable for ytk.** A function `region_vectors(tokens, masks)` in
  `experiments/patch_grid/` (not yet in `ytk/`), and a note in the README of
  storage per image (46 x 1152 fp16, about 100 KB) and query cost (one
  matmul).

### 2. Section 55: the long tokens — about 1.5 hours

The most publishable thread: the registers phenomenon on an attention-pooling
head, which no verified source has measured.

- **Setup.** Hooks on every encoder layer's output norm for the 40 cached
  gate images plus the ten. Norm threshold from the registers paper: 150.
- **Three pictures, in order, each sent as it lands.**
  1. Per-layer: fraction of tokens above the threshold at each of the 27
     layers, one line per image in DIM, the mean in GOLD. Where do they
     emerge; compare with the paper's 37 percent depth and the CLIP result's
     layer 6 of 12.
  2. Where they sit: the positions of the high-norm tokens over all 50
     images accumulated on one 24 x 24 grid. The spike suggested the border;
     this is the test.
  3. What hiding them does: reuse section 54's masking to exclude the
     high-norm tokens from the probe. Cosine between the embedding with and
     without them, per image, as a distribution; and the probe's attention
     map before and after on two images.
- **Then the test-time fix.** Try arXiv 2506.08010's neuron relocation
  (code at github.com/nickjiang2378/test-time-registers) on this checkpoint.
  If the repo does not support SigLIP-2 out of the box, spend at most 30
  minutes adapting it; otherwise record that as the stopping point.
- **More figures.** (4) After the fix, the same three pictures again on
  the same images, laid beside the before, so the effect of relocation is
  read as a change in shape. (5) The tokens themselves: for the ten images,
  the high-norm patches ringed on the image, so the owner can see what
  pixels they sit on.
- **Readout.** Counts and depths in the README's meta lines. If hiding the
  tokens moves the embedding by more than 0.01 cosine on most images, that
  is a finding about production search and goes into the write-up with its
  distribution.
- **Dead end.** No layer shows a clean emergence, or hiding them changes
  nothing (cosine above 0.999 everywhere) and the probe map is no more
  legible.

### 3. Section 56: a sturdier referee — about 1 hour of GPU

- **Whole-object occlusion.** Cover each SAM region in turn, re-encode,
  record the drop: 46 passes, about 25 s per image, all ten. This is the
  necessity map at object resolution and it is what section 54's maps are
  compared with.
- **RISE on three images only.** Random multi-region masks, 2,000 per image
  at about 11 minutes each, in a tmux window. The three: the woman, the
  goat (frame-filling subject, where single-region occlusion failed), and
  one of the six new ones with a small object.
- **The picture.** One row per image: sliding occlusion, whole-object
  occlusion, RISE, for the same query, one colour scale. The claim is
  visible in whether the goat lights up under RISE.
- **More figures.** (2) All ten images, sliding against whole-object
  occlusion for the small-object query, one row each. (3) For the goat, the
  RISE map at 200, 500, 1,000 and 2,000 masks in a row, so convergence is
  visible and the mask count is justified by the picture and not by habit.
- **Readout.** Spearman between whole-object occlusion and RISE per image,
  reported as numbers in the README, not as a gate. If they agree above 0.7
  on all three, sliding and whole-object occlusion are adequate referees and
  RISE is not needed again.
- **Dead end.** RISE and the cheaper occlusions rank regions the same way,
  which is a useful negative and ends the referee question.

### 4. Section 57: SAM 3 on this machine — about 45 minutes, may fail fast

- **Install** from the transformers main branch into a scratch environment
  (`uv run --with "transformers @ git+..."` into `/tmp`, never into the
  project env). If it needs Triton or fails to load on MPS, record the error
  verbatim and stop; that is the result.
- **If it loads:** time one image on MPS, then run the two queries the
  two-model recipe missed on the woman image: "sunglasses" and "the whole
  woman". Picture: SAM 3's mask against the masked-head winner for each.
- **Figures.** If it loads: the woman image, SAM 3's mask against the
  section 54 winner for each of the two queries, plus the two queries it
  handles that section 54 could not (the printed caption, the whole person).
  If it does not load: no figure is faked; the README carries the error and
  the section has no lead PNG, which the record's rules already allow for
  a section that failed at install.
- **Readout.** Seconds per image on MPS and peak memory. The verdict the
  brief asked for: whether it belongs in ytk at query time, or only in the
  boxing project on the 3070.
- **Dead end.** More than a few seconds per image, or memory pressure
  alongside SigLIP-2.

### 5. Section 58: the whole-encoder gradient lens — about 45 minutes

Only after section 55, because the long tokens are expected to dominate a
naive gradient.

- LeGrad-style (arXiv 2404.03214): gradient of the image-text cosine with
  respect to every layer's attention, accumulated. One forward and backward
  per image-query pair, nothing cached.
- **The picture.** The ten images, the small-object query, gradient lens
  against whole-object occlusion from section 56.
- **More figures.** (2) One image, the gradient lens accumulated layer by
  layer, all 27 layers as a strip, so where the map forms is visible. (3)
  The agreement distribution over the ten images, drawn with each image's
  mark, against the section 53 lenses on the same axis so the improvement,
  if any, is a visible shift.
- **Readout.** Spearman per image against the section 56 referee, as a
  distribution. This is the one place a number is the finding, because the
  question is whether an instant, uncached method can replace the referee
  for a single-image view.
- **Dead end.** Median Spearman below 0.3.

## What the owner sees in the morning

- One commit per section on `exp/53-patch-grid`, each with figures, a README
  and a row in `docs/experiments.md`; a comment per section on #218.
- A short closing note appended to this file: which sections ran, which hit
  a dead end, total GPU minutes, and the one decision that is his: whether
  section 54's region vectors go into `ytk/visual.py` behind a flag.
- No merge, no reinstall, no hub restart. The hub keeps serving master.

## Budget

| Section | GPU | Wall |
|---|---|---|
| 0 | none | 30 min |
| 54 | about 5 min | 1 h |
| 55 | about 10 min | 1.5 h |
| 56 | about 40 min | 1 h |
| 57 | unknown, capped at 45 min | 45 min |
| 58 | about 5 min | 45 min |

About an hour of GPU, five to six hours of session time. No Claude API
calls beyond the session itself. The 3070 is not used; nothing here needs
it, and the owner has not said whether that machine is his to use.

## Not in scope tonight

Training anything. Changing `ytk/` or the hub. The 40-image gate: it is
closed, not rerun. Sparring footage, unless the owner adds frames to the
image list before go. Any experiment whose first picture is not readable.
