# 47 — The GEN gate (rung 7 of #183)

**Question.** GEN mode would render a latent as an image via
latent -> decoder direction -> Qwen space -> a linear translator -> CLIP
space -> unCLIP. Every pixel of that chain is only as trustworthy as the
translator, so the translator is gated behind its own pre-registered
experiment before any image is generated. A failed gate closes GEN mode and
is itself the section (the record has published three registered losses).

## Pre-registration (written before any measurement)

**Data.** The 5,071 doc-level notes, embedded twice: the production Qwen
vectors (cached), and OpenAI CLIP ViT-L/14 text embeddings of the same
cached text prefixes. Disclosed limitation: CLIP's 77-token context reads
roughly the first 300 characters of each note — the pairing is
head-of-note to head-of-note.

**Translator.** Ridge regression Qwen (1024d) -> CLIP (768d), fit on a
random 80% split (seed 47), evaluated on the held-out 20%.

**Registered gate.** For each held-out note: its top-10 neighbors among all
docs in native CLIP space, versus its top-10 in CLIP space when the query
side is its *translated Qwen* vector. Agreement = |overlap| / 10.

- **PASS: mean agreement >= 0.40** on the held-out notes — the translated
  vector finds at least four of the ten neighbors CLIP itself would name.
- **Control:** the same translator fit on shuffled (Qwen, CLIP) pairs must
  score near zero; if the control scores within 0.10 of the real
  translator, the result is void regardless of the bar.
- unCLIP renderings happen only on PASS, always as calibrated triples
  (0.5x / 1x / 2x, T4), each image stamped with the translator's measured
  agreement, and register features carry the confabulation warning
  on-card.

Numbers land in `gen_translator.json`; the runner is
`experiments/sae_qwen/gen_translator.py`. Results follow below this line
only after the gate has run.

---

## Result: FAIL — GEN mode stays closed

Measured on 1,015 held-out notes (`01-the-gate.png`):

- **Mean agreement 0.22** (median 0.20, p10 0.00) against the registered
  bar of 0.40.
- **Control 0.0096** — the real translator scores 23x the shuffled-pairs
  fit, so the linear map genuinely carries Qwen structure into CLIP space;
  the control condition is comfortably met. The signal is real. It is not
  enough.
- The distribution's honest detail: a long tail of notes translates well
  (some exceed 0.7 agreement), but the mass sits left of the bar, and a
  renderer that is right about a minority of notes cannot stamp its images
  trustworthy.

This is the record's fourth registered loss, and it closes rung 7 the way
the epic specified: no unCLIP model was downloaded, no image was generated,
and every number the decision rests on was registered before the translator
existed. Plausible upgrades (a larger CLIP text tower, nonlinear maps,
training on full-note CLIP embeddings via chunk pooling rather than the
77-token head) are future experiments with their own pre-registrations —
none of them may inherit this section's bar retroactively.

The atlas keeps its two honest modes: TEXT is measurement, IMG is evidence.
There is no paraphrase mode, and the display contract says so.
