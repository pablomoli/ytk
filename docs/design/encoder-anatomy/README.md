# Encoder anatomy — the frog and its organs

Status: registration in progress (2026-10-31). Nothing here has run. This
document holds the verified ground the program stands on, the map of the
organism, and the predictions, nulls and bars for each dissection, written
before the first call. Each dissection becomes a numbered section in
`docs/assets/` when it runs; this file is the plan, not the record.

## Why

Fifty-seven sections study the production encoder's output. None opens the
encoder. Section 18's "layers" are Gemma Scope features from another model.
The vectors that every map, search and memory in ytk runs on come out of one
model whose interior has never been looked at on this corpus. This program
opens it, one organ at a time, in the Welch Labs grammar: name the part,
watch it work on one real specimen, remove it, see what the animal can no
longer do.

## The organism (verified 2026-10-31 from the model's own config)

`Qwen/Qwen3-Embedding-0.6B`, loaded through sentence-transformers in
`ytk/store.py`.

| Organ | Measured fact |
|---|---|
| token table | vocabulary 151,669, width 1024 |
| blocks | 28, each: RMSNorm, attention, RMSNorm, feed-forward, both adding into the residual stream |
| attention | 16 query heads over 8 key-value heads (grouped), head size 128 |
| feed-forward | width 3072 |
| residual stream | width 1024, the same width as the shipped vector, so every layer's state already lives in the space the map is drawn in |
| final norm | RMSNorm, eps 1e-6 |
| pooling | last token only (`1_Pooling/config.json`: `pooling_mode_lasttoken: true`, `include_prompt: true`); the whole note is squeezed through one position |
| the shipped vector | 1024 floats, unit length, compared by raw cosine in Chroma (`hnsw:space: cosine`, three collections) |

Specimen: Welch Labs, *The moment we stopped understanding AI [AlexNet]*
(`UZDiGooFs54`), chosen by measurement in section 42 and held through
sections 42 to 46. The T2 discipline, one example never switched, continues.

## The findings this program leans on — re-verified

Each row: what the record claimed, when, and what the same measurement says
today. "then" numbers are read from the sections' own `results.json`; "now"
numbers come from the sections' own analysis code pointed at a fresh harvest
of the live store (scratchpad, nothing in `docs/assets/` rewritten).

| Finding | Section | Then | Now (2026-10-31) | Holds? |
|---|---|---|---|---|
| the cone: mean vector 11x longer than chance, every note near one direction | 12 (2026-07-28, 493 notes) | mean pair cos +0.259, mean vector length 0.510 (chance 0.045, 11.3x), every note at cos 0.51 to the shared direction, PR 104/1024 | 811 notes: mean pair cos +0.259, mean vector length 0.509 (chance 0.035 at this n, 14.5x), cos to shared direction 0.51, PR 115/1024 | yes; the length 0.51 and the 0.26 are the stable facts, the "x chance" grows with n because chance is 1/sqrt(n) |
| raw geometry reads 8.4x more structured than centred | 15 (2026-08-02, same 493) | 8.4x chance on the record's one pair (0, 250); centred 2.0x | that pair reproduces at 8.4x; over 50 random pairs the median is 7.5x frozen and 7.4x live, centred 2.1x both | yes; "about 8x" is the honest phrasing, the single pair sits a little above typical |
| 58 of 69 tags cohere raw, all 69 centred | 10, 12 | 58/69 raw (84%), 69/69 centred | 84 scorable tags now: 70/84 raw (83%), 84/84 centred | yes |
| production retrieval is raw cosine, no centring | 19 | kept | `ytk/store.py` creates every collection with `hnsw:space: cosine`; no centring anywhere in the search path | yes |
| the gate: 156 known-answer queries over a frozen corpus | 08 | hit@1 0.712, hit@5 0.904, hit@10 0.942 (stamped 2026-07-26, 11,005 frozen ids) | passed 2026-10-31: hit@1 0.712, hit@5 0.897, hit@10 0.936 (within the 0.02 tolerance); live store 20,675 docs; 6 queries' frozen windows starved by newer docs; 39 s wall | yes |
| the vault is used, the hub is not | 40 (2026-08) | 57 elective reads of 671, 1 cited, loops close in sessions | not re-measured; nothing since changed the hub's role | assumed |
| labels too thin to train anything | inventory (2026-09-18) | 92 answers in two sittings, 31 items, 0 drop | 114 answers (45 with text), 46 items, 1 drop; 84 of 114 still from 09-06 and 09-08; 419 hub verdict rows exist | yes, still thin |
| no section opened the production encoder | 18 | Gemma Scope layer 20 | confirmed by grep; `output_hidden_states` appears nowhere in `ytk/` or `scripts/` | yes |

## The organ map

`organs.html` beside this file is the interactive map: the note's path from
the vault through the token table, the repeated block (attention,
feed-forward, residual stream), the final norm and last-token pooling, into
Chroma and the search the agents call, with the gate under it. Built with
archify from `archify/candidate.json`; every repo-backed box cites its lines
at commit `97095ff`. The organs inside the model cite the Hugging Face config,
not the repo. Rebuild after an edit with:

```
node ~/.claude/skills/archify/bin/archify.mjs finalize architecture \
  docs/design/encoder-anatomy/archify/candidate.json \
  docs/design/encoder-anatomy/organs.html --repo-root . --quality showcase --json
```

## The dissections

Three cuts, ordered by cost. Each one is a record section when it runs. The
shared rules: the specimen is never switched; every panel pairs the specimen
with the population (section 34's lesson: the individual makes it legible,
the population makes it true); every number has a null drawn in DIM; the
prediction below is written before the first call and stands on the page
whether it holds or not.

### D1. The shipped vector's coordinates, and the centred exam

**Question.** Is the shared lean (section 12's cone, mean vector length 0.51)
carried by a few loud coordinates, or spread across many? And, the question
section 19 left open and handed to the gate: does subtracting it help search?

**Why it might go either way.** Timkey and van Schijndel (EMNLP 2021) found
that one to three "rogue" dimensions dominate similarity in BERT and GPT-2.
Sun et al. (COLM 2024) found at most four "massive activations" per hidden
state in LLaMA-2 that behave like fixed biases. Both argue for "a few loud
coordinates". Against them: this model's output is trained contrastively on
cosine of this exact vector, and section 12's participation ratio of 104
says the centred variance is spread. The ratio concerns the variance, not the
mean, so the mean's shape has never been looked at.

**The figure.** Panel 1: the 1024 coordinates of the mean vector, sorted by
magnitude, as a bar field, with the isotropic null's sorted coordinates in
DIM. Panel 2: the specimen's own 1024 coordinates on the same axis, the
cone's top coordinates marked. Panel 3: the gate's hit@k, raw against
centred, as two distributions over bootstrap resamples of the 156 queries,
the baseline's 0.02 tolerance drawn as a band.

**Prediction.** Spread. The top 3 coordinates carry under 10% of the mean's
squared length and the top 100 carry under 60%. On the exam, centring moves
hit@5 and hit@10 by less than the tolerance (section 19 measured +1.2 points
on tag agreement, which is a different ruler; the registered expectation is
"inside the noise").

**Null.** Isotropic unit vectors, same n and d, 300 draws: the top-k share of
the mean's squared length (expected near k/1024). Second null for coordinate
identity: shuffle coordinates within each note, 300 draws, same statistic.
For the exam the null is the baseline itself with its tolerance.

**Bar.** "Rogue" if the top 3 coordinates carry at least 50% of the mean's
squared length; "spread" if the top 100 carry under 60%; anything between is
reported as mixed. On the exam, centring earns the search slot only if hit@5
and hit@10 both exceed the baseline by more than 0.02 and hit@1 does not
fall. This is the same bar the gate applies to every retrieval change.

**Cost.** Zero model runs for the coordinates: the vectors are in Chroma. The
exam embeds 156 queries once (seconds), then scores in numpy over the 20,675
stored vectors restricted to the 11,005 frozen ids, through
`retrieval_gate.evaluate` with custom searchers. Under five minutes.

**Ships if it passes.** A centred search path behind the epoch mechanism in
`ytk/store.py` and a deliberate re-stamp of the baseline. If rogue, centring
is zeroing three coordinates and the orb can paint them.


> **Later (2026-10-31, section 58):** ran as registered. Spread: top 3 carry 4.3%, top 100 carry 49.9% (isotropic null 3.1% and 43.3%); the prediction held and the mean's profile is nearly the noise profile. The exam: raw reproduces the stamp exactly, centred scores 0.686 / 0.904 / 0.929, hit@1 falls past the tolerance with the paired interval touching zero; not earned, production stays raw cosine. The "if rogue, the orb can paint them" branch is closed. Record: `docs/assets/58-encoder-anatomy-d1/README.md`.

### D2. The residual stream across depth

**Question.** Where in the 28 blocks is the cone born, where do topics
separate, and would the exam prefer an earlier stop?

**Why it is open.** Ethayarajh (EMNLP 2019) found contextual representations
anisotropic in every layer of BERT, ELMo and GPT-2, most extreme in GPT-2's
last layer. That is a causal language model's interior; this encoder is a
causal Qwen3 whose top was tuned contrastively for last-token pooling.
Whether the tuning sharpens or flattens the cone at the top is unknown.

**The figure.** The growth film: 29 frames (the token table's output, then
each block), every note placed by one projection fitted on the final layer
and held fixed, so motion is the representation changing and never the
projection. Beside it, two lines over depth with their nulls in DIM: the
mean vector's length (the cone) and leave-one-out nearest-centroid accuracy
over the 84 scorable tags. The specimen wears its thread through all 29
frames.

**Per-layer vector.** At block k, the last position's residual state, passed
through the final RMSNorm, unit-normalised: "where this note would land if
the encoder stopped here". Mean-over-positions pooling is drawn as a
disclosed side panel, never the main claim.

**Predictions.** (1) The cone is present at every layer and its length rises
with depth to a maximum at or within two blocks of the last; the tuning does
not remove it. (2) Tag accuracy rises with depth and reaches 90% of its
final value by block 20, saturating before the top. (3) No single earlier
block beats block 28 on the exam; an average of the last four blocks lands
within tolerance of it.

**Nulls.** For the cone: isotropic draws per layer. For tag accuracy: labels
shuffled, 300 times, per layer. For the exam: the baseline and its
tolerance.

**Bars.** A layer "separates topics" when its accuracy exceeds the shuffled
null by z > 3. The "saturation block" is the first at 90% of final accuracy.
A layer or average ships only under D1's exam bar.

**Cost.** Rung A, the 811 tagged notes: one forward pass with hidden states,
about 15 minutes on MPS at the recorded second per vector (migration spec,
2026-07-16), 48 MB in half precision. Rung B, the exam: the 11,005 frozen
documents, about 3 hours, 650 MB, run in a visible tmux pane overnight. Rung
B runs only if rung A shows a candidate layer, and only on a separate go.

**Ships if it passes.** A pooling change in `ytk/store.py` as a new epoch, a
65-minute re-embed, a deliberate re-stamp.


> **Later (2026-11-01, section 60, rung A):** both predictions failed in the same direction. The cone is at full strength at the token table (every note ends in the same token, mean length 1.00) and is eroded with depth, 0.74 after block 27 and 0.51 after block 28, so its maximum is at depth 0, not the top. Tag accuracy reaches 90% of its final value at depth 26, not by block 20; every depth separates topics beyond z = 24. Mean pooling leads until block 20 and loses at the top. The note is written in the last third of the network and block 28 does the largest single share. Rung B ran on the owner's blanket go of 2026-11-01 (119 min for the frozen corpus): the gate is blind through depth 9, hit@1 is 10% at depth 18, 25% at 21, 71% at the top; no earlier depth ships (best hit@1 before the top is 0.635 at depth 26) and the mean of the last four depths is inside tolerance at 0.699 / 0.917 / 0.949, so prediction 3 holds; the final block is load-bearing for hit@1 and dispensable for hit@5 and hit@10. Record: `docs/assets/60-encoder-anatomy-d2/README.md`.

### D3. The summarizing heads

**Question.** With last-token pooling, one position carries the note. In the
final blocks, which heads fill it, from which words, and what happens to the
note's place on the map when one head is switched off?

**Why it is open.** Xiao et al. (ICLR 2024) showed decoder models park a
large share of attention on the first token regardless of its meaning, the
attention sink. Whether the heads that write the summary are the ones that
avoid the sink has not been measured on an embedding model.

**The figure.** Panel 1: for the specimen, a 28 by 16 grid of the last
position's attention, each cell the share of mass on position 0 (the sink)
against content positions. Panel 2: the same grid coloured by ablation
effect, the cosine between the shipped vector with that head zeroed and the
original. Panel 3: the specimen's top-10 neighbours before and after
removing the single most consequential head, drawn on the map. Population
panel: the same two grids averaged over 20 notes drawn by stratified sample
from the 84 tags.

**Predictions.** (1) In blocks 20 to 28 the median head puts more than half
its last-position attention on position 0. (2) Fewer than 45 of the 448
heads move the specimen's vector below cosine 0.95 when zeroed, and the five
largest movers all sit in the last eight blocks. (3) Across heads, ablation
displacement and sink share are negatively rank-correlated, rho below -0.3:
the heads that summarise are the ones that read the words.

**Nulls.** Uniform attention gives position 0 a share of 1/n (0.2% at 477
tokens). For ablation, a matched null: zero 128 random coordinates of the
concatenated head outputs at that block, 100 draws, same displacement
statistic. For the population claim, a head counts only if it moves at least
3 of the top-10 neighbours on at least 15 of the 20 notes.

**Bars.** A head is "summarising" when its ablation changes at least 3 of the
specimen's top-10 neighbours and its displacement exceeds the matched null's
99th percentile. The finding is real when the population bar above holds.

**Cost.** Attention weights need `attn_implementation="eager"` (the default
SDPA path returns none); the model loads once through
sentence-transformers as `model[0].auto_model`. Specimen: 448 ablation
passes of 477 tokens, about 5 minutes. Population: 20 notes, about 80
minutes, its own go.

**Ships if it passes.** Nothing. This one is the frog, and the material of
the record section.


> **Later (2026-10-31, section 59):** ran on the specimen. One of three predictions held: the sink is there from block 4 (8 of 9 late blocks' median above 0.5, block 27 at 0.36); only 4 heads move the vector below cosine 0.95, but the five largest movers sit in blocks 3, 1, 18, 14, 14, not the last eight; Spearman of displacement against sink share is -0.67. Block 3 head 6 carries the cone: zeroed, the note falls to cosine 0.22 to itself and 0.15 to the shared direction, outside the population. The population run inherits two questions: is it the same head on every note, and does it write the sink. Cost: 51 min, not 5; a batch of 16 costs 16 single passes on Metal, so the population run must budget 20 x 51 min or drop the per-block null to 10 draws. Record: `docs/assets/59-encoder-anatomy-d3/README.md`.

## Order, cost, and gos

| Step | Model calls | Wall time | Go needed |
|---|---|---|---|
| D1 coordinates | none | minutes | ran 2026-10-31, section 58: spread |
| D1 centred exam | 156 query embeddings | under 5 min | ran 2026-10-31, section 58: not earned |
| D2 rung A, 811 notes | one pass with hidden states | about 15 min (ran 21) | ran 2026-11-01, section 60 |
| D3 specimen | 1 + 448 passes, one note | about 5 min (ran 51: batching scales linearly on Metal) | ran 2026-10-31, section 59 |
| D3 population, 20 notes | 20 x 449 passes | about 80 min | yes |
| D2 rung B, the exam per layer | 11,005 docs with hidden states | about 3 h (ran 2 h) | ran 2026-11-01, section 60.2 |

Everything above reads the store and never writes to it. Nothing in
`docs/assets/` is rewritten; each run gets its own numbered section.

## Literature (checked 2026-10-31)

- Ethayarajh, "How Contextual are Contextualized Word Representations?",
  EMNLP 2019, arXiv:1909.00512. Anisotropy in every layer; extreme in GPT-2's
  last layer; under 5% of variance in a word's first principal component once
  anisotropy is adjusted for.
- Timkey and van Schijndel, "All Bark and No Bite: Rogue Dimensions in
  Transformer Language Models Obscure Representational Quality", EMNLP 2021,
  arXiv:2109.04404. One to three dimensions dominate similarity; standardisation
  offsets them.
- Sun, Chen, Kolter, Liu, "Massive Activations in Large Language Models",
  COLM 2024, arXiv:2402.17762. At most four activations per hidden state,
  roughly fixed across inputs, acting as biases and pulling attention.
- Xiao et al., "Efficient Streaming Language Models with Attention Sinks",
  ICLR 2024, arXiv:2309.17453. Strong attention to initial tokens regardless
  of their meaning.
