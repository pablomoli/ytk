# 44 — Atlas binning (rung 3 of #183)

**Question.** Bin the frozen map into cells and give each a latent identity —
then say, per cell, how much of that identity survives retraining, how much
of the activation the named head explains, and how much of the cell the
checkpoint has never seen.

**Data.** The frozen 08-11 layout (`~/.ytk/map.json`, 5,080 points; 5,016
joined to the Aug-8 vector cache by vault path and video id), the three final
SAE checkpoints, `features.json` names. Computed by
`experiments/sae_qwen/atlas_bin.py` (12x12 lattice, cells kept at >= 15
scored notes, excess via the rung-1 `excess_profile` with its 200-draw null);
rendered by `scripts/plot_atlas_cells.py`. Ships `atlas.json` here and to
`~/.ytk/atlas.json` (the continents/galaxy/channels pattern). Read-only;
production search untouched.

## Findings

**The map has local vocabulary (figure 01).** 62 cells clear the size
threshold and carry 52 distinct top-excess latents — the atlas is not one
loud latent painted everywhere. #977 "EpicMap field service SaaS" labels
five contiguous cells (the work continent); the YouTube side fragments into
one-cell identities. Cell labels whose latent was outside the named head
were named through the same Haiku pipeline before the final render.

**The gate: 36/62 labels survive retraining (figure 02, left).** A label
survives if the seed-1 and seed-2 dictionaries both contain a direction
among that cell's top-5 excess latents matching the s0 label at decoder
cosine >= 0.5 (20/62 at 0.8; the strict top-1-only variant passes 21). The
instability is not noise, it is geography: stable cells concentrate where
head-explained mass is high (figure 02, middle — up to 50% on the work side,
~10% on the content side), which is rung 2's finding one level up —
frequency buys stability, and cells fed by head latents relabel stably while
tail-labeled cells shuffle. The atlas draws the distinction per cell instead
of averaging over it.

**Disclosures (figure 02, middle and right).** Median head-explained mass
25%; the named head is a minority shareholder in most cells — the
dark-matter caveat as a per-cell number. Median OOD 0%, concentrated in the
few cells where new notes have been landing since Aug-8 (peak 19%).

**The protagonist has a home it was never given (figure 03).** The AlexNet
note postdates the frozen layout (captured 08-14, map generated 08-11), so
its cell is a 10-NN vote among joined notes — stated as an estimate,
CYAN-dashed on figure 01. Independently, #1597's per-cell excess drawn as
terrain has exactly one ridge (1/62 cells outside its null), and the
estimated home cell sits on that ridge: the embedding-neighbor vote and the
activation geography agree without being asked to.

## Figures

- `01-named-lattice.png` — the atlas: cells, identities, stability in the
  label weight, protagonist cell dashed CYAN.
- `02-trust-panel.png` — per-cell stability / head-mass / OOD.
- `03-protagonist-terrain.png` — #1597's excess field as relief; the cyan
  post is the estimated home cell.
