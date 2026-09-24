# 58 — The whole-encoder gradient lens (#218)

**Question.** Section 53's gradient lens ran through the pooling head only
and scored 0.13 against the referee. LeGrad (arXiv 2404.03214) takes the
gradient of the image-text score with respect to every layer's attention
map, clamps the negatives, and accumulates over layers; Grad-ECLIP (arXiv
2502.18816) weights intermediate features by their gradient. Both see the
encoder before the global mixing the head-only lens is blind to. One
forward and one backward per image-query pair, nothing cached: if it
tracks the referee, it is the instant lens for a single-image "show me
where" view. Run after section 55 so the three register slots could be
zeroed from the map, as the plan's amendment asked.

Section 5 of the patch-grid night, `docs/design/patch-grid-night/README.md`.

## What was done

- The production model with the attention implementation switched to
  eager for the run, a forward hook on every layer's self-attention keeping
  its (1, 16, 576, 576) weights with their gradient, and one on every
  layer's output keeping the residual tokens. Score: cosine of the pooled
  vector with the query text. One backward per pair; 30 pairs in 70 s.
- **Attention variant.** ReLU of the gradient on the attention weights,
  averaged over heads and over the 576 query rows, one 24 x 24 map per layer
  over the key patches, averaged over the 27 layers. LeGrad reads the CLS
  token's row; this encoder has no CLS, the probe pools outside the
  encoder, so every row is averaged. That choice is disclosed on the figure
  and it is what makes the variant flat (below).
- **Gradient x activation.** For each layer's output tokens, the gradient
  times the activation summed over channels, negatives clamped, one map per
  layer, averaged over layers; then the same with the three register slots
  of section 55 zeroed.
- **Referees.** Section 56's whole-object occlusion on the 24 x 24 grid
  (each patch takes the largest drop of any region that owns it) on all
  ten, Spearman over the 576 patches; RISE on the three images that have it.
  The small-object query throughout.

## Result

**Dead end: median Spearman +0.07 and +0.01 against a bar of 0.30.**

- **The attention-gradient map is flat by construction.** Its peak patch
  holds 0.2 percent of the map on every image, which is 1 of 576: averaging
  the clamped gradient over every query row gives each key its share of the
  area and nothing else. The goat's patches take 5 to 8 percent of the map
  at every layer against the goat's 5 percent of the frame. The per-image
  correlations that look large (-0.61, +0.45) are what a flat map scores
  against a referee that is zero on most patches. Figure 01, column 2.
- **Gradient x activation is speckle.** Peak patch 2 to 10 percent of the
  map, scattered single patches at every layer, no hill forming anywhere
  along depth (figure 02, all 27 layers on the goat). Spearman with the
  object referee: median +0.01, range -0.11 to +0.17; with RISE on the
  three images +0.17, -0.13, +0.17. Zeroing the slots changes nothing that
  matters: they hold 0 to 2 percent of the averaged map (25 percent at the
  last layer alone), and the median stays +0.01. Figure 03 puts these
  beside section 53's three lenses on their own referee; the new lens is no
  better than the old ones and worse than the head-only gradient.
- The grad x attention product, tried while diagnosing the flat map and
  not kept as a variant, concentrated on patches 408, 384 and 20, the
  three register slots, at every layer from 10 on: the slots are where the
  score's gradient meets the attention, which is one more way of seeing
  section 55's finding.

**Reading.** On an attention-pooled encoder the whole-encoder gradient has
nowhere to read from. LeGrad's map is the CLS row's, and the CLS row exists
because the score is a function of the CLS token; here the score is a
function of a probe that lives outside the encoder, so no row inside the
encoder is privileged and the aggregate is uniform. Gradient x activation
on the residual tokens is not uniform, but on this checkpoint it is noise
with the register slots on top. The instant single-image lens this section
was for does not exist in this form; the lenses that located objects in
this record all paid for encoder passes (crop-on-grey, occlusion, RISE).

## Not done

- A probe-weighted row aggregation (weight each layer's query row by the
  probe's final attention on that token) is the obvious next adaptation of
  LeGrad to a MAP head. It was not tried; the plan set one run and a dead
  end, and the head's attention is itself the section 53 lens 1 that
  scored 0.02.

## Figures

- `01-the-lens-against-the-referee.png` — all ten, small-object query:
  attention gradient, gradient x activation raw and with slots zeroed, the
  whole-object referee; Spearman in the corners.
- `02-where-the-map-forms.png` — gradient x activation on the goat, all 27
  layers and their mean.
- `03-agreement-against-section-53.png` — per-image Spearman for the three
  variants, with section 53's lenses on their own referee for scale.

Cache `~/.ytk/patch_grid/night/58_legrad.npz`; runner
`experiments/patch_grid/run58.py`; figures `scripts/plot_night.py 58`.
