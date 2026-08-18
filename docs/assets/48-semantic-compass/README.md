# 48 — The semantic compass (rung 7', part 1)

**Question.** Section 47 closed GEN mode: a learned bridge between spaces
could not earn trust. This is the replacement bet: a paraphrase channel with
**zero learned parameters** — a small set of semantic axes constructed from
the corpus by disclosed recipes, giving every object in the system (a note,
a latent's decoder direction, an atlas cell, a live query) the *same
signature form*: a compass rose. If the axes are real, one glyph reads
everywhere.

## Pre-registration (written before any measurement)

**The five axes.** Each is a contrast-of-means over the cached doc-level
unit vectors — subtracting two means cancels whatever the whole corpus
shares, so the cone never enters. Recipes, in full:

| axis | pole A | pole B |
|---|---|---|
| SPOKEN <-> WRITTEN | youtube video notes | web-article notes |
| SCROLL <-> SIT | instagram + tiktok notes | youtube + web notes |
| MINE <-> WORLD | vault-authored memories (source = vault) | ingested content (youtube/web/instagram/tiktok) |
| FRESH <-> SETTLED | newest date quintile | oldest date quintile (dates via the map join) |
| CODE <-> PROSE | text head contains a code marker (backtick fence, "def ", "() {", "=>") | no marker |

Axis vector = unit(mean(A) − mean(B)). A signature = the 5 projections of a
unit vector onto the axes, drawn as a rose.

**Registered gates.**

- **G1, validity:** for each axis, fit the contrast on a random half of its
  labeled notes (seed 48) and score the held-out half: ROC AUC **>= 0.80**
  per axis, and the label-shuffled null must sit below 0.60. An axis that
  fails is dropped and its dropping is reported; the compass survives with
  >= 4 axes or the section is a loss.
- **G2, signature stability:** for 200 random notes, the 5-d signature from
  split-A axes vs split-B axes must agree at mean cosine **>= 0.90** — the
  rose must not depend on which half of the corpus defined it.
- **Disclosure (not gated):** the pairwise |cosine| matrix of the five axis
  vectors, so correlated axes are visible rather than implied independent.

Numbers land in `axes.json`; runner `experiments/sae_qwen/semantic_axes.py`.
Results follow below this line only after the gates have run.
