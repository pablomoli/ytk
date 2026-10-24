# 55 — The long tokens (#218)

**Question.** Section 53 found that a few of SigLIP-2's 576 patch tokens are
about eight times longer than the rest before the final layernorm, that they
hold a fifth of the pooling probe's attention, and that they keep it after
the pixels under them are greyed. That is the registers phenomenon of Darcet
et al. (arXiv 2309.16588): high-norm tokens that carry global rather than
local information, emerging at about 37 percent depth in large ViTs, in
about 2.4 percent of patches. No verified source had measured it on SigLIP-2
or on any attention-pooling head. Where do they emerge in this encoder,
where do they sit, what does hiding them do to the vector ytk searches with,
and does the test-time register of Jiang et al. (arXiv 2506.08010) work here?

Section 2 of the patch-grid night, `docs/design/patch-grid-night/README.md`.

## What was done

- **Fifty images.** The night's ten plus the 40 gate thumbnails of
  section 53. One forward pass each with a hook on every one of the 27
  encoder layers, recording each token's norm at each layer's output. The
  threshold for "long" is 150, the paper's. `run55.py norms`, 26 s.
- **Hiding.** Section 54's masked head with the long tokens excluded from
  the probe, cosine against the production vector, per image; and the same
  with an equal number of random tokens hidden instead, as the null.
  `run55.py hide`, CPU.
- **Register neurons.** The repository at github.com/nickjiang2378/
  test-time-registers supports OpenCLIP and DINOv2 and adds a model by
  copying its code and writing a hook manager; that was not done. Its
  algorithm (`shared/algorithms.py`, 82 lines) was reimplemented against the
  HF module with forward hooks in under the plan's 30 minutes: for every MLP
  neuron in every layer, mean absolute activation at the long-token
  positions minus mean elsewhere, averaged over the ten images. Then two
  interventions from the paper: zero the top neurons at every position
  (ablation), or append one zero token after the patch embeddings and, in
  the MLP, set the top neurons' activation on it to the signed maximum they
  reached on any image token while zeroing them on the image tokens (the
  test-time register). Measured on the ten: norms along depth, cosine of the
  pooled vector to production, the probe's attention. `run55.py registers`
  and `run55.py attention`.

## Result

**They emerge at 37 percent depth, all at once, at the same three positions
in every image.**

- No token exceeds 150 through layers 1 to 9. At the output of layer 10
  (10 of 27, 37 percent depth, the paper's number to the percent) two tokens
  jump from a norm of about 10 to about 2,100 and hold it, unchanged, to the
  end; a third joins at the last layer. Ordinary tokens grow from 8 to 64
  over the same depth. Figure 01; every one of the fifty grey lines lies
  under the gold mean, so the shape is the checkpoint's, not the image's.
- The positions are fixed: (row 0, col 20), (row 16, col 0), (row 17, col 0)
  on the 24 x 24 grid, in 50 of 50 images, and no other position ever
  crosses the threshold. All three are on the border, which is what the
  spike guessed. Figure 02; figure 05 rings them on the ten pictures so it is
  visible that the content under them is grass, a grey desk, a stone wall,
  or sky.
- **Hiding them from the probe moves every production vector.** Cosine
  between the pooled vector with and without the three: median 0.979,
  minimum 0.948, all 50 below 0.99. Hiding three random tokens instead:
  median 1.0000, minimum 0.9992. Three tokens of 576, holding 10 to 21
  percent of the probe's attention on the ten images, carry about 2 percent
  of the vector's direction. Figure 03. The probe's attention map without
  them is not more legible: the top ten patches drop from 25 to 21 percent on
  the woman image and the speckle stays.
- **Nine neurons make them.** Of the 27 x 4,304 MLP neurons, nine in
  layer 10 score 180 to 212 and nothing else scores above 82 (one neuron in
  layer 27, which fits the third token appearing there). The paper found
  about ten of 37,000 in OpenCLIP ViT-B/16 after layer 6 of 12; here it is
  nine of 116,000 at layer 10 of 27. Figure 04.
- **The test-time register works.** Zeroing the top ten neurons removes
  every long token (largest image-token norm 126) but moves the pooled
  vector to cosine 0.85 with production: the model needs whatever those
  neurons compute. Shifting the top 30 onto one appended zero token also
  removes every long token from the image (largest norm 123), the register
  itself reaches norm 2,200, the probe gives it 8 percent of its attention,
  and the pooled vector stays at cosine 0.977 median (0.954 minimum) with
  production, the same distance as simply hiding the three. The attention
  map over the image is still speckle (top ten patches 18 percent). Figure
  04, bottom row.

**Reading.** SigLIP-2 so400m/16 at 384 has three built-in register slots at
fixed border positions, written by nine neurons in layer 10 and never
moved by the picture. Anything that reads the 24 x 24 grid has to know
this: the spike's "the probe's favourite tokens sit on high-contrast
patches" was a coincidence of which border patches those were, and section
54's masked head handed those slots to whichever region contained them.
For ytk's search vector the finding is a number: the three slots carry
about 0.02 of cosine, and every image pays it. The dead-end condition (no
clean emergence, or cosine above 0.999 everywhere) did not fire; the plan's
hope that hiding them would make the probe map legible did not come true
either.

> **Later (review, 2026-10-24, `run55.py review` and the saved caches):**
> four sentences above say more than the data.
>
> - **Two slots are written at layer 10, not three.** (row 16, col 0) and
>   (row 17, col 0) jump to about 2,100 at layer 10. (row 0, col 20) is at
>   norm 10 at layer 10 and 40 at layer 26, and crosses 150 only at the last
>   layer (median 245, minimum 162). The result bullet says so; the reading
>   and the plan's closing note do not.
> - **The nine, ablated alone.** The first pass only intervened on the top
>   3, 10 and 30. Zeroing just the nine layer-10 neurons leaves 0.2 tokens
>   above 150 per image (the slots peak at 153, 109 and 96) at cosine 0.856
>   with production (minimum 0.767): the nine make the two layer-10 slots,
>   causally. Shifting the nine onto a register removes those two (peaks 101
>   and 78) and leaves the third (281, one per image) at cosine 0.977. The
>   first pass's top-10 shift, not reported above, left 0.8 long tokens per
>   image (largest 188), which is why the reported shift used the top 30.
> - **"2 percent of the vector's direction"** is 0.02 of cosine. Cosine
>   0.979 is an angle of about 12 degrees, and the part of a unit vector
>   that changes is about 0.20 of its length.
> - **The null was weak.** Three random tokens hold about 0.5 percent of
>   the probe's attention; the slots hold a median 12.7 percent. Hiding the
>   three most-attended tokens that are not slots instead (median 7.3
>   percent of the attention) moves the vector to a median cosine 0.991
>   (minimum 0.960): 43 percent of the slots' effect for a little over half
>   their attention. Plotted against the attention hidden, the two sets lie
>   on one rising trend where their shares overlap (figure 06): much of what
>   hiding the slots does is what hiding any heavily attended tokens does,
>   and the slots are where most of that attention sits.
> - **"Every production vector"** is the 50 measured, recomputed through the
>   CPU head from fp16 tokens, not read from the stored production vectors.
>   With the positions fixed in 50 of 50 the effect plausibly holds for
>   every image; it was not measured on every image.
> - **Novelty is scoped to the sources the brief verified.** Work on
>   position-fixed artifacts in ViTs (for example "Denoising Vision
>   Transformers") was not checked against this result before the claim was
>   written.
> - The second "Not done" item below was done the same night: section 54's
>   addendum masked the slots out of every region. It moved two of 19 picks.

## Not done

- The register variant was not evaluated on retrieval or the gate. Whether a
  0.977 vector searches as well as the production one is a section of its
  own, and `ytk eval` is the instrument for it.
- Whether the three slots hold anything that helps the masked head of
  section 54 if masked out region by region. One experiment, deferred.

## Figures

- `01-where-they-emerge.png` — longest and median token norm along the 27
  layers, fifty images; the count above 150 along depth.
- `02-where-they-sit.png` — positions accumulated on the 24 x 24 grid, and
  the mean last-layer norm per position.
- `03-what-hiding-them-does.png` — cosine with and without the three, fifty
  images, random-three null in grey; the probe's attention before and after
  on two images.
- `04-a-test-time-register.png` — neuron scores along depth, norms along
  depth under production, ablation and shift; how far each moves the vector;
  the attention maps under each.
- `05-the-tokens-themselves.png` — the three patches ringed on the ten
  images with their norms.
- `06-a-null-that-carries-attention.png` — the review's null: the slots
  hidden against the three most-attended other tokens hidden, and how far
  each moves the vector against the attention it took away.

Caches `~/.ytk/patch_grid/night/55_*.npz`; runner
`experiments/patch_grid/run55.py`; figures `scripts/plot_night.py 55`.
