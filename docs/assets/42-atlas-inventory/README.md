# 42 — Atlas inventory (rung 0 of #183)

**Question.** Before the activation atlas builds anything: do its inputs
actually exist, how far does each reach over today's corpus, and which latent
is the protagonist — chosen by measurement, not taste?

**Data.** The Aug-8 native SAE (`experiments/sae_qwen/`, d=2048, k=32, seed 0
checkpoint, recon cosine 0.825), its 16,483-vector training cache, the live
Chroma store, the frozen Phase-12 map layout (`~/.ytk/map.json`, 5,080
points), and `features.json` (top-100 latents named by Haiku). Everything
read-only; numbers in `rung0.json`, produced by
`experiments/sae_qwen/rung0_inventory.py`.

## Findings

**Coverage (figure 01).** The live store holds 18,755 vectors; 12.1% of them
postdate the training cache (video notes 15.2%, segments 15.8%, memories
1.5%). Nothing the SAE trained on has left the store. The segment store
covers 405/407 video notes (99.5%), so rung 4's activation strips have their
data. Thumbnails cover 594/5,080 map points (11.7%) — concentrated in the
YouTube continent (group 38, 30%) and one small group at 68%; most groups
sit under 5%, so the feature wall will be mostly `[T]` typographic tiles, as
#183 predicted.

**Checkpoint decision.** The epic's lean is adopted: keep the Aug-8
checkpoint for rungs 0-5 (12% unseen is disclosure territory, not
invalidation — every atlas cell will state its OOD fraction per #183's
display contract), and refresh as its own later section with a before/after.

**No cone in the native dictionary (figure 02, left).** Not one of the 2,048
latents fires on even half the corpus; the most frequent (#1983, "designing
systems around model strengths") reaches 15.8%, median breadth is 218
documents, and no latent is dead. Section 18's "31 always-on latents"
belonged to a different SAE over a different vector set; under TopK
competition the shared cone direction lands in the decoder bias and the
pre-activation offsets, not in nameable always-on latents. Consequence for
#183: there is no subtraction list — the excess-over-base-rate null on cells
(rung 3) carries the whole burden the cone subtraction was going to share.

**The protagonist (figure 02, right).** The AlexNet note's loudest latent is
**#1597, activation 0.219** — outside the top-100 frequency head, so it was
named through the same Haiku pipeline as the head
(`experiments/sae_qwen/name_latents.py`, appended to `features.json`):
*"educational breakdown of language model mechanics"*, high confidence, top
exemplars Karpathy's ghosts talk, "I Built an LLM From Scratch", and
3Blue1Brown's transformers chapter. Runners-up #1211 *"sparse autoencoders
and mechanistic interpretability"* and #1310 *"transformer architecture and
tokenization"*, both high confidence. A Welch Labs interpretability video
whose loudest latent is educational-breakdown-of-LM-mechanics is the
protagonist thread #183 asked for. #1597 wears CYAN here and in every
subsequent atlas figure.

## Figures

- `01-coverage.png` — what the checkpoint has seen; where the wall can show
  pictures.
- `02-protagonist.png` — the cone check that legitimizes "loudest", and the
  note's top-12 fingerprint head.

Rendered by `scripts/plot_atlas_rung0.py`; sidecar `rung0.json`.
