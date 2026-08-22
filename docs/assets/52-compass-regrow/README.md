# 52 — Regrowing the compass (rung 7'', part 1)

**Question.** Section 48 registered a five-axis compass and lost it 3-2. This
asks whether the two dead axes died of the corpus or of their recipes, and
rebuilds both from the property itself rather than from a proxy for it.

## What the pilot found before anything was registered

Three facts were measured first, disclosed here because they changed the
design. None of them touches a gate.

**The section 48 loss replicates on today's corpus.** The same runner, the
same seed, a cache re-pulled from the live store: same three axes pass, same
two die, same FAIL. Three months of growth moved the written pole from 21
notes to 28 and the code pole from 10 to 10.

| axis | s48 (poles) | today (poles) |
|---|---|---|
| scroll-sit | 0.90 (251/366) | 0.92 (270/456) |
| mine-world | 0.97 (4449/617) | 0.97 (4510/726) |
| fresh-settled | 0.92 (1316/955) | 0.92 (1352/966) |
| spoken-written | 0.95 (345/**21**) | 0.90 (428/**28**) |
| code-prose | 0.75 (**10**/5061) | 0.85 (**10**/5231) |

So the thin poles are not a young vault. They are the recipes.

**Doc-level register is constant, which makes section 48's reading of
spoken-written wrong.** A 42-note stratified pilot labeled 39 written to 3
spoken. Inspecting the store explains it: Chroma embeds a YouTube note's
*enrichment* — thesis, summary, key concepts — and not its transcript. The
`## Transcript` fold is in the vault note, not in the embedded document. Every
doc vector in the corpus is composed prose, whoever composed it.

A contrast between two sets that share a register cannot be measuring
register. Section 48 recorded that axis as real signal killed by a thin null;
it is better read as **provenance signal wearing a register label** —
separating video-derived from article-derived notes by topic and phrasing.
Section 48 is annotated in place; its own bar does not move.

**The spoken pole exists one collection over.** The 14,254 segment vectors are
transcript text — filler, direct address, mid-sentence boundaries — at a median
1,029 characters against 1,620 for note documents, so the two are comparable in
length rather than differing in granularity.

> **Corrected after the run:** that last clause is wrong, and it is the claim
> that let this design through. Comparing two medians is not comparing two
> distributions. Measured properly the poles are nearly disjoint in length —
> segments p10-p90 760-1,199, notes 1,283-1,974, bands that do not intersect —
> because chunking caps segments near 1,200 characters and enrichment notes
> begin above it. A classifier given nothing but character count scores AUC
> 0.977 on this contrast. The error is left standing above and answered by a
> control below; the registered gates are untouched by it.

## Pre-registration (written before any gate ran)

**The five axes.** Recipes in full. Two are rebuilt; three are unchanged from
section 48 and are expected to reproduce.

| axis | pole A | pole B | fit |
|---|---|---|---|
| SPOKEN <-> WRITTEN | a video's transcript segments | that same video's enrichment note | ridge probe |
| SCROLL <-> SIT | instagram + tiktok notes | youtube + web notes | contrast-of-means |
| MINE <-> WORLD | vault-authored memories | ingested content | contrast-of-means |
| FRESH <-> SETTLED | newest date quintile | oldest date quintile | contrast-of-means |
| CODE <-> PROSE | Haiku `code_bearing` true | Haiku `code_bearing` false | ridge probe |

The register axis is **paired within video**: both poles are drawn from the
same videos, so speaker and topic are held constant and only register varies.
This is the control section 48's recipe lacked.

Labels come from `register_labels.py` — `claude-haiku-4-5` via
`ytk.sdk.structured`, judging the full document text pulled from Chroma rather
than the 900-character head whose blindness produced the 10-note code pole.
The labeler is never told a note's source. Labels at `confidence: low` are
dropped before any fit, per the minority-class warning in arXiv 2504.15432.
Code labels are drawn from a **stratified sample of ~1,200 doc notes**, not a
census; poles are therefore sample-derived and disclosed as such.

**Fit protocol**, fixed here so nothing downstream is a free parameter:

- Split 50/50, stratified by class, seed 52. For the register axis the split
  is **by video**: every segment of a video lands on the same side as that
  video's note, so no video appears in both fit and held-out.
- Ridge-regularized logistic probe where a pole is small or paired
  (arXiv 2408.03414, tens-of-shot regime); contrast-of-means where both poles
  are large. Which applies is fixed per axis in the table above.
- The majority class is subsampled to the minority size within the fit set.
- Ridge strength C is chosen by 5-fold CV **on the fit half only**, over the
  fixed grid [0.01, 0.1, 1, 10, 100]. The held-out half is never consulted.
- Axis vector = unit(probe coefficients) for a probe, unit(mean A − mean B)
  for a contrast. A signature = the projections of a unit vector onto the
  kept axes, drawn as a rose.

**Registered gates.**

- **G1, validity, per axis:** held-out ROC AUC **>= 0.80** and a per-axis
  permutation p-value **< 0.05** over 200 label shuffles, computed as
  (1 + #{null >= observed}) / (1 + 200). This replaces section 48's fixed
  null ceiling of 0.60, which scaled with pole size and so killed an axis at
  n = 21 for being small rather than for being wrong.
- **Compass verdict:** **>= 4 of 5** axes pass. Same bar as section 48,
  freshly registered.
- **G2, signature stability:** for 200 random notes, signatures from
  split-A axes and split-B axes agree at mean cosine **>= 0.90**.
- **Disclosure (not gated):** pairwise |cosine| of the kept axes; pole sizes
  before and after confidence filtering; the label confidence distribution;
  and the fit method actually used per axis.

**Registered in advance:** a compass that survives on 4 axes but loses the
register axis is a different instrument from one that keeps it, and the
section will say which it got rather than reporting "4 of 5" alone.

Numbers land in `axes_regrow.json`; runner
`experiments/sae_qwen/semantic_axes_regrow.py`. Results follow below this line
only after the gates have run.

---

## Result: the compass regrows, 5 of 5

**Every axis clears the registered bar** (`01-the-gates.png`). Each observation
is drawn inside its own 200-shuffle null; the nulls sit on 0.50 and the
observations sit past 0.80, and the gap between them is the finding.

| axis | poles | fit | held-out AUC | null median | p |
|---|---|---|---|---|---|
| spoken <-> written | 14,254 / 426 | ridge, C=100, split by video | **0.9951** | 0.50 | < 0.005 |
| scroll <-> sit | 270 / 456 | contrast-of-means | **0.9100** | 0.50 | < 0.005 |
| mine <-> world | 4,510 / 726 | contrast-of-means | **0.9728** | 0.50 | < 0.005 |
| fresh <-> settled | 1,352 / 966 | contrast-of-means | **0.9124** | 0.50 | < 0.005 |
| code <-> prose | 907 / 310 | ridge, C=1.0 | **0.9201** | 0.50 | < 0.005 |

G2 passes: signature stability mean cosine **0.9565**, p10 0.8972, across
disjoint defining halves — above section 48's 0.92 on a compass with two more
axes. Verdict **PASS**, and the register axis is one of the five that carried
it, which the pre-registration required be stated rather than folded into "4 of
5".

Every p-value is 0.00498 because that is the floor of a 200-shuffle test,
1/201: no permutation ever reached the observation. Read them as p < 0.005, not
as five separate precise quantities.

## The axis that had to survive a second question

The gate could not have caught the real threat to spoken-written. Section 48
died of a name that did not match its recipe, and this axis was at risk of
exactly that a level down: segments are chunks and notes are summaries, so a
probe could score 0.995 by reading **size** and never touch register. The
pre-registration's claim that the poles were "comparable in length" was wrong —
they are nearly disjoint, and length alone scores 0.977 (`02-the-confound.png`,
left panel).

Two controls, neither registered and neither a bar:

- **Caliper matching.** Pairing each note with a segment within 10% on length
  collapses the length-alone baseline from **0.977 to 0.678**, while the
  embedding probe holds at **0.961** (216 pairs; 210 notes had no segment their
  length, so the matched set is the short half of the notes). A length detector
  would have fallen with its crutch. This is an upper bound rather than a clean
  number: a 10% caliper still leaves 0.678 of length signal in the matched set.
- **An independent judge.** Haiku, which never sees whether a row is a segment
  or a note, reads segment text as spoken **191 to 9**, and doc notes as
  written **1,209 to 11**. The poles differ in register by a judgement made
  from the words alone, not from the schema.

A third control would have settled it outright — verbatim speech stored as a
note, dissociating register from format — and was not available: the corpus
holds one voice-memo note.

## What is disclosed rather than claimed

- **The five axes are not five independent directions.** Pairwise |cos|:
  mine-world/code-prose **0.544**, fresh-settled/code-prose 0.387,
  mine-world/fresh-settled 0.321, spoken-written/scroll-sit 0.298, the rest
  below 0.2. The code axis leans on the mine-world axis because the
  code-bearing notes are largely vault-authored. A rose drawn on these five
  spokes shows fewer than five degrees of freedom.
- **The code pole is sample-derived.** 1,220 usable labels from a stratified
  1,200-note draw (11 API failures, 3 dropped as low-confidence), not the
  5,241-note census. `code_confidence` came back off-enum — `medium-high`,
  `low-medium` — because the field was typed as free text; the filter drops the
  low family, and both counts are in `axes_regrow.json`.
- **The corpus is not section 48's.** The cache was re-pulled from the live
  store after the old one was destroyed, so the three unchanged axes are
  re-measured rather than quoted. They reproduce section 48 closely (0.90/0.97/
  0.92 there, 0.91/0.97/0.91 here), which is the reason to trust the two new
  ones.

Data: `axes_regrow.json`, `register_control.json`. Runners:
`semantic_axes_regrow.py`, `register_control.py`, `register_labels.py`.
Figures: `scripts/plot_compass_regrow.py`.
