# 43 — The feature wall (rung 2 of #183)

**Question.** The atlas needs a head it can trust: are the top-100 latents
coherent objects that survive retraining, and how much of their evidence can
be shown as pictures rather than asserted in prose?

**Data.** `features.json` (top-100 by firing frequency, Haiku-named),
`seed_agreement.json` (per-latent min-over-seeds max decoder-row cosine,
computed by `experiments/sae_qwen/seed_agreement.py` from the three final
checkpoints), vault thumbnails, and the s0 decoder. Rendered by
`scripts/plot_feature_wall.py`; sidecar `wall.json`.

## Findings

**The head is the stable part of the dictionary (figure 01).** 59/100 head
latents survive retraining at decoder cosine >= 0.8 and 89/100 at >= 0.5 —
against 7% and 20% corpus-wide (rung 0 measured the full 2048). Frequency
buys stability: the latents that fire most are the ones whose directions
reproduce across seeds. Every tile wears its own badge, so a reader can
discount any single tile without discounting the wall.

> **Later (section 49):** the mosaics were re-rendered with one exemplar
> per note — segments repeat their parent video's thumbnail, so the original
> tiles overstated the evidence. Distinct-image coverage is **45.9%**; the
> paragraph below records the original, inflated number as written.

**The wall's evidence is 55.9% pictures.** 502 of 899 mosaic cells carry a
real thumbnail; the rest are `[T]` provenance tiles (letter = Vault, Web,
Instagram, TikTok). Rung 0 predicted a mostly-`[T]` wall from map coverage
(11.7%); the head's exemplars skew hard toward YouTube segments, so the wall
is half pictures — a measured surprise in the pleasant direction.

**Coherence is visible, not asserted (figure 02).** Each latent's own top-4
exemplars against 4 drawn at random from the head's pooled exemplar set:
every real tile reads as one topic (#1597: three copies of "I Built an LLM
From Scratch" plus Karpathy; #977: four EpicMap notes), every shuffled tile
reads as the corpus. The protagonist's tile is outlined CYAN, keeping the
section-42 thread. Protagonist badge: 0.57 — middling stability, stated on
the tile like everyone else's.

**Carried caveat.** Names remain exemplar-derived hypotheses (section 24's
contract); the wall shows the evidence for each name next to it, which is
the most a static figure can do. Causal validation is rung 6's knob.

## Figures

- `01-wall.png` — the top-100 head: decoder image + exemplar mosaic + badge
  per tile, ranked by firing frequency.
- `02-coherence-null.png` — real vs shuffled exemplar assignment, TEXT mode,
  protagonist outlined.
