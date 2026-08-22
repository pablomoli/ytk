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

---

## Result: a registered loss, with a surviving instrument

**As registered, the compass fails: 3 of 5 axes survive and the bar said 4**
(`01-the-gates.png`).

- scroll-sit **0.90**, mine-world **0.97**, fresh-settled **0.92** — all
  pass with shuffle nulls at ~0.50.
- spoken-written scored AUC **0.95** — real signal — but failed the
  registered null clause: its written pole has only 21 web notes in the
  cache, and a 21-note pool makes the shuffle null's p95 reach 0.61. The
  axis died of my recipe's thin pole, not of absent structure.

  > **Later:** section 52 found this reading wrong, and wrong in a way the
  > thin pole hid. Chroma embeds a YouTube note's *enrichment* — thesis,
  > summary, key concepts — not its transcript; the `## Transcript` fold
  > never reaches the store. Every doc vector in the corpus is composed
  > prose, so both poles here share a register and the contrast cannot have
  > been measuring one. A 42-note Haiku pilot labeled the doc corpus 39
  > written to 3 spoken, and re-running this exact runner on a corpus grown
  > to 28 web notes still reproduces the loss. The 0.95 is better read as
  > **provenance signal wearing a register label** — video-derived notes
  > separating from article-derived ones by topic and phrasing. The axis did
  > not die of a thin pole; the pole was thin *and* the name never matched
  > the recipe. Section 52 rebuilds it as a within-video contrast — a
  > video's transcript segments against that same video's note — which holds
  > speaker and topic constant so only register varies. The loss recorded
  > here stands, and its bar does not move.
- code-prose was degenerate: the lexical rule found 10 positive notes in
  the 900-character text heads. Ten notes cannot anchor a direction.
- G2 passed: signature stability mean cosine **0.92** across disjoint
  defining halves.

The loss stands — no bar moves after the data. What survives is a
**three-axis compass** whose axes are near-orthogonal (pairwise |cos| 0.01,
0.01, 0.32) and whose glyph is legible on real objects
(`02-the-surviving-compass.png`): the AlexNet note reads SIT+WORLD
(ingested longform — correct), latent #977's decoder direction reads MINE
(work — correct), and the corpus mean collapses to a dot, as an honest
reference should. Whether to adopt the three-axis instrument, and whether
to re-register spoken-written with an adequately pooled written pole once
more web notes are cached, are owner decisions; neither inherits this
section's bar.

