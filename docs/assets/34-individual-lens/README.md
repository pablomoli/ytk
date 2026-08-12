# 34 — The individual lens

Three record findings re-shot after studying Welch Labs' *The Dark Matter of
AI* (ingested 2026-08-12; the study is
[`docs/research/2026-08-12-welch-labs-visual-grammar.md`](../../research/2026-08-12-welch-labs-visual-grammar.md)).
The video's grammar — render the vector itself as an image, follow one
concrete example through the whole system, keep a readout on screen, show
interventions as calibrated before/after pairs — is the inverse of this
record's: the record proves things about populations against nulls and almost
never shows an individual. This section tests whether the individual lens
adds anything the population figures don't, by pairing his moves with the
house null discipline in the same panels.

The question, precisely: **can a single real note carry a finding the record
has so far only stated statistically?**

## The seriation readout

Every vector image in this section uses one pixel order: dimensions sorted by
the corpus mean's coordinate magnitude, values sign-aligned to the mean, so
the shared direction (the cone, sections 12/16/17) concentrates in the top
rows. This is an instrument, and it is disclosed in every meta line. The null
is the same transformation under 300 random pixel orders.

The naive Welch claim died in checkpoint before the first figure was drawn:
in native dimension order, raw and centered vectors are indistinguishable —
the cone's largest single coordinate is 0.06 on a unit vector. The strongest
geometric fact about this corpus is invisible in the raw object. That failure
chose the section's shape: the individual lens works here only *with* a
readout, which is itself the video's third technique.

## Figures

**01 — The cone, held up to the light** (remix of 16/17). The corpus mean as
a 32×32 image (a smooth gradient under seriation, with its 32 loudest dims as
row 0); one note in native order (structureless), seriated (top band
visible), and centered (band gone). Row-profile panels put the individual
against the population and the null: this note's raw profile exits the
random-order band for the first ~6 rows (row 0-2 mean 0.037 vs null 5-95%
±0.02), its centered profile sits at 0.0015; the 568-note median does the
same. **One note is enough to see the cone — once the pixels are sorted by
it.**

**02 — One note through the whole system** (remix of 12/18). The section's
running individual is the video's own note. Its stored document (1639 chars →
424 tokens) → Qwen3 vector with real values → 32×32 image → retrieval readout
→ Gemma-Scope fingerprint (16,384 features as 128×128, computed on the 18.2
rig by `scripts/fingerprint_one_note.py`, same MAX_CHARS=2000 cut as the
batch) → population histograms. Findings: the note is a typical citizen (L0
5370 vs population median 5282; cone mass 0.125 vs 0.113); its loudest
feature is 9622 "references to convolutional neural networks and their
capabilities" — the note about reading networks with SAEs is itself read by
an SAE, correctly; and its nearest neighbors are its own reference list
(`toy-models-of-superposition` 0.605, `on-the-biology-of-a-large-language-
model` 0.604), papers ingested weeks before the video that cites them.

**03 — The road, watched instead of scored** (remix of 20). Section 20 scored
the ai-agents → machine-learning road in aggregate (support, bridges); this
figure walks it with the readout on screen. The film strip draws each stop as
its **difference from the start** — change is what is drawn, so the walk is
visible (flat at t=0.17, full texture by t=1.0). Below, the top-3 retrieved
notes per stop, and the crossing cos-to-endpoint curves. Top-1 changes hands
4 times; the nearest-note cosine declines monotonically 0.793 → 0.737 with no
mid-road spike, consistent with 20's finding that this pair has no bridge
notes. **The walk is a handover, not a fade.**

## Caveats

- The seriation order is fitted on the same 568 notes it displays. Fine for
  an exhibition of a known finding (the cone was established with proper
  nulls in 12/16/17); it would not be evidence of a *new* structure.
- The one-note fingerprint reuses the 18.2 rig configuration (MPS) without
  re-running the rig-validation gate; the rig was validated against the
  Neuronpedia API in 18.1 and unchanged since.
- Figure 03's strip mixes scales: panel 0 is the centered start (absolute),
  panels 1-6 are deltas on their own symmetric limit. Both are stated on the
  panels.
- Retrieval in 02/03 is raw cosine over the frozen 568, not the production
  searcher — same convention as section 20, so the numbers are comparable
  within the record but not gate scores.

## Reproduce

```
uv run --with matplotlib python scripts/plot_individual_lens.py        # all three
uv run --with sae-lens --with torch python scripts/fingerprint_one_note.py  # regenerate the npz
```

Inputs: `17-corpus-growth/{vectors-fresh.npz,tags-fresh.json}`,
`18-sae-fingerprints/{manifest.json,fingerprints.npz,cone-features.json}`,
and this directory's `darkmatter-fingerprint.npz` + `feature-names.json`
(Neuronpedia explanations for the note's top features, fetched 2026-08-12).

## What the lens is worth

The pairing is the lesson: the individual panel makes the finding *legible*
(you can point at the row, the pixel, the handover stop) and the population
panel makes it *true* (the null band, the medians). Neither replaces the
other. Candidates for the same treatment later: a calibrated clamp of a
native-SAE latent with retrieval before/after (the video's 100-vs-500 move,
proposed independently by the audit for sections 18/21/24), and section 19's
six metrics as six seriated similarity images.
