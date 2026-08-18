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
