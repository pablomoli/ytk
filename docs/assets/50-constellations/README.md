# 50 — Constellations (owner's conjecture: the code has a shape)

**Question.** Every code lights exactly 32 of 2,048 latents, but the code
image scatters them by latent index — an ordering that means nothing, so
the picture has no shape to read. The owner's proposal: canonicalize the
dimension. Give every latent a fixed position derived from what it means,
and a note's code becomes 32 stars in semantic space — a constellation
whose *shape* is a property of the note. Focused notes should cluster;
bridging notes should sprawl. Is that real, or does any 32-of-2,048 look
the same?

## Pre-registration (written before any measurement)

**The canonical layout.** 2D PCA of the 2,048 unit decoder rows (centered,
deterministic SVD, sign-fixed), frozen alongside the checkpoint. Latent
positions never change between notes, so shapes are comparable — the same
discipline as the frozen map.

**The shape statistic.** Coherence of a code = activation-weighted mean
pairwise cosine among its active latents' decoder rows (computed in the
full 1024-d decoder space; the 2D layout is display only, and the figure
says so).

**Registered gate — G1, shape is not chance.** For 500 sampled notes:
each note's coherence against 100 frequency-matched nulls (32 latents
drawn with probability proportional to corpus firing frequency, the
note's own activation weights reassigned to them). PASS if **>= 60% of
notes exceed their own null's p95**. Below the bar, constellations are
decoration and the section says so.

**Disclosed, not gated.** Whether coherence tracks anything (note kind,
the protagonist thread's neighbors) is exploratory this section; any
pattern found here must be re-registered before it is claimed.

**The share transform (same section, owner's second proposal).** Displayed
neighbor cosines compress into a narrow band because all pairs float on
the corpus background (0.26, section 12). Where ranked winners are shown,
they gain a share column: softmax((sim - max)/T) with **T = the standard
deviation of the background-pair null**, so the temperature is measured,
not tuned. Raw cosine stays printed beside it — the transform re-scales
contrast, never replaces the magnitude.

Numbers land in `constellations.json`; runner
`experiments/sae_qwen/constellations.py`. Results follow below this line
only after the gate has run.

---

## Result: PASS at 89% — the code has a shape

- **G1: 89% of 500 sampled notes exceed their own frequency-matched null's
  p95** (bar 60%); median observed coherence 0.029 vs median null p95 0.014
  (`01-the-shape-gate.png`). A code's 32 latents genuinely huddle in decoder
  space — the shape is the note's, not the dictionary's.
- **The constellations are readable as connectivity, not as scatter**
  (`02-four-constellations.png`): 2D flattens most of the huddle, so the
  figure draws the statistic itself — an edge wherever two active latents'
  decoders agree past cosine 0.15. The EpicMap work note webs at 45 edges,
  the AlexNet note holds 25, the hydration listicle frays to 12, and the
  frequency-matched chance draw is dust at 4. Coherence is edge count.
- **The share transform shipped**: background doc pairs measure mean 0.309,
  std 0.106 — that std is now the softmax temperature wherever ranked
  winners display (the passport's company column, the hub knob's lists,
  carried as data in `atlas_sae.npz` so it is never re-typed). Raw cosine
  always prints beside the share.
- Exploratory, not claimed: coherence looks like a focus dial (work note
  0.070 > protagonist 0.034 > listicle -0.004). Any use of that pattern
  gets its own registration first.
