# 53 — Syntax laws (the forest, rung 0)

**Question.** Before drawing this repo's code as a forest, do its syntax trees
obey the branching laws that real trees and river networks obey? If they do,
the rendering rules can be derived from the laws with one fitted constant each
instead of tuned by eye. If they do not, the drawing has to say so.

Corpus: every `.py` under `ytk/` and every non-test `.ts`/`.tsx` under
`web/src`, parsed with tree-sitter, named nodes only, files under 20 nodes
dropped. 216 files, 301,018 nodes, 0 parse errors. Script:
`scripts/measure_syntax_laws.py` writes `measured.json`;
`scripts/plot_syntax_laws.py` draws the three figures. Commit `c8b41dd`.

## Pre-registration

Written in chat from a six-file pilot (Neovim's own tree-sitter, counting
nodes per Strahler order), before the corpus script existed:

1. Subtree sizes are Zipfian: rank-size slope −1 in every file.
2. Branching has two regimes: bifurcation ratio near 2 at low Strahler
   orders (expressions), 4–7 at high orders (blocks).
3. Half of every tree is leaves, mean fan-out 2.

**The null.** For each file, 20 uniform random plane trees with the identical
out-degree multiset, built by the cycle lemma (shuffle the degrees, rotate to
the unique valid preorder). It keeps fan-out and leaf count exactly and
randomizes what the grammar imposes: which children sit under which parents,
depth, subtree sizes, Strahler structure. Prediction 3 is therefore not a test
against this null; it is fixed by construction. Predictions 1 and 2 are.

## What the corpus said

| quantity (per-file medians) | Python | TypeScript | TSX | null |
|---|---|---|---|---|
| files / nodes | 81 / 184,099 | 80 / 65,520 | 55 / 51,399 | |
| leaf fraction | 0.49 | 0.43 | 0.43 | same |
| rank-size slope | −0.98 | −1.07 | −1.18 | −1.59 / −1.41 / −1.50 |
| power-law tail α (MLE, xmin 2) | 1.67 | 1.70 | 1.69 | 1.52 / 1.56 / 1.54 |
| max depth | 16 | 16 | 23 | 65 / 33 / 42 |
| files shallower than own null | 81/81 | 79/80 | 55/55 | |
| bifurcation ratio, orders 1→2 | 3.4 | 3.2 | 3.4 | 4.8 / 4.4 / 4.6 |
| bifurcation ratio, orders 4→5 | 5.7 | 4.0 | 4.0 | 4.0 / 3.0 / 3.0 |
| length ratio, orders 1→2 | 1.7 | 1.6 | 1.6 | ≈1.9 |
| length ratio, orders 4→5 | 0.9 | 0.7 | 1.1 | ≈1.8 |

**Figure 01 — depth.** Max depth against file size, every file and its twenty
nulls. Real depth grows like n^0.15; the null's like n^0.47, the square-root
law of random trees. 215 of 216 files sit below their own null's mean, median
z −3.3 for Python. The grammar builds bushes where chance builds spines: a
block holds many statements side by side, a call holds its arguments side by
side, and nothing in Python or TypeScript lets a spine run.

**Figure 02 — Zipf.** Every file's rank-size curve over its subtrees, with its
nulls in grey. Real files run at slope −1 in a band of ±0.1; the nulls run at
−1.5 with a plateau of near-root-sized subtrees and a cliff. Prediction 1
holds, and the null says why it matters: −1 is not a property of trees, it is
the grammar's. Random trees with the same degrees do not have it.

**Figure 03 — Horton.** Bifurcation and length ratios by Strahler order,
medians with interquartile bands. Horton's laws say both ratios are constant
across orders; rivers sit near R_B 4, R_L 2. The null obeys them almost
exactly: R_B 4.7 → 3.7 with a gentle fall, R_L flat near 1.9. The real trees
break both in one direction: R_B rises with order (3.4 → 5.7 in Python) and
R_L falls below 1 by order 3 (1.7 → 0.9). Low-order streams are long chains
(expression nesting), high-order streams are short and fan wide (a module of
top-level definitions, a body of statements).

## Corrections

**Prediction 2 was an artifact, and the finding it pointed at is real but
lives in a different ratio.** The pilot counted *nodes* per Strahler order.
Horton's ratio counts *streams*, maximal chains of equal order. Counting nodes,
a chain of ten order-1 nodes is ten; counting streams it is one, and the
"bifurcation ratio near 2" at low orders was the chains being counted as
branches. Under the proper definition R_B at orders 1→2 is 3.4, not 2, and
there is no knee. What the pilot was seeing survives as the *length* ratio
falling below 1: twigs are chains, limbs are fans. The two-regime language in
the design chat is withdrawn; the direction is kept.

**"Half of every tree is leaves" is not a finding against this null.** The
degree-matched null keeps leaf count exactly. It is a fact about the grammar
(named fan-out is near 2) and it fixes the leaf fraction of any drawing, but
no shuffle can contradict it. A different null, a Galton–Watson tree with a
fitted offspring distribution, would test it; not run here.

## What it fixes for the drawing

Three rules derived, one fitted constant each, none tuned by eye:

- **Radius from subtree size** through the area-preserving split. The Zipf
  slope of −1 says the size distribution is scale-free, so one exponent gives
  self-similar thickness at every zoom. α ≈ 1.7 is the tail to reproduce.
- **Length from Strahler order** through the *measured* length ratio, which
  falls with order. A tree drawn with Horton's constant R_L 2 would put the
  long segments at the top; this corpus puts them at the twigs. The drawing
  must use the falling ratio or it draws the null.
- **Depth is the crown, not the trunk.** Depth ∝ n^0.15 means even the
  20,951-node `cli.py` is 28 deep. Height cannot carry file size; girth and
  crown volume must. That is the metabolic-scaling question for the next rung.

## Rung 4 spike outcome (parked 2026-09-14)

Drawn under the three rules with nothing else tuned, two files read as trees
at once; a 66-file stand followed. The owner's read: they look like corals,
and that became the vision. Eight versions are recorded on #217; the
regenerable code is `labs/syntax_forest_spike/` and the last page is
https://claude.ai/code/artifact/945807c6-5ff2-495f-8492-7a3a1611714c.
Two lessons that bear on the bake: a height-dependent translation field is a
shear and reads as stretching, so branches must move as rigid links; and the
area law puts nearly all mass in a short stub at the module node, which is
rule 3 made visible and the reason height cannot carry size. Parked before
rung 1; nothing from the spike is a finding.

## Next

- Genome: the 206-type vocabulary per file, clustering into species without
  language or directory as input; the prediction is that role (route, helper,
  CLI, renderer) separates before language does.
- The grammar footprint ring: each language's `node-types.json` as sectors,
  filled by this corpus's usage, with the negative space as the dialect never
  spoken. Rarity from this becomes the palette.
- A Galton–Watson null for the leaf fraction and the Zipf tail, so prediction
  3 gets a real test.
