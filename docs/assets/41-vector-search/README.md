# 41 — Vector search from first principles (#184)

**Question.** Take Exa's example project literally at this project's scale:
we depend on an index we have never built once and had never timed. Brute
force over the production store, then a 10M synthetic corpus matched to the
real geometry, then earn the speed back stepwise — memory layout,
quantization, coarse indexing, a systems-language kernel — with recall
priced against a frozen referee at every step. Speed bought with recall is
reported, never hidden.

**Data.** The production store (18,755 vectors at measurement, 1024d), and
`~/.ytk/e41/`: a 10M-vector float32 memmap (38.1GB) sampled from the real
corpus's mean + scaled PCA basis (the impostor validated in figure 02:
pairwise cosines within 0.001, participation ratio 124 vs 130), an int8
mirror with per-vector scales, and the referee — 1,000 queries (500 real,
500 held-out synthetic) with exact top-100 ground truth. Runner
`scripts/e41_vector_search.py`; kernel crate `experiments/e41_kernel/`.
Ground-truth rows are ascending by score; the one instrument bug of weekend
1 (a reader taking the head, scoring recall 0.000) is documented at
`_recall_at_10` and the ordering contract is now stated at the definition.

## The ladder so far (weekend 1, measured)

| rung | layout | bytes/vec | single query | recall@10 |
|---|---|---|---|---|
| baseline 18k | f32, exact | 4096 | 1.56ms (Chroma: 12.3ms) | 1.0 by definition |
| 0 — brute 10M | f32 memmap, exact | 4096 | 98.3s | 1.0 by definition |
| 1 — int8 | int8 + per-vector scale | 1028 | 31.7s | 0.9836 |
| 2 — PQ | 64 codebooks x 16d | 64 | 2.4s | 0.161 |

The shape of the wall (figures 03-04): exact search falls off a cliff and
the cliff is the disk — 38.1GB streamed per sweep at an effective 0.39GB/s,
while 20 batched queries cost one sweep. int8 buys 3x for a 1.6% truth tax.
PQ64 fits the whole corpus in 640MB of RAM and answers in 2.4s, but keeps
16% of the truth — the gap between rung 2 and rung 1 is the work.

## Pre-registration, weekend 2 (written before any measurement)

Six predictions, committed before the runs. None is a ship gate — the
section ships whatever the numbers say — but each is falsifiable and the
misses will be reported with the hits.

- **P1, centered PQ64: no change.** Recall@10 within 0.02 of rung 2's
  0.161. K-means is translation-equivariant — shifting every vector by the
  corpus mean shifts the centroids with it, and the constant q·mu cannot
  reorder a ranking. The variant runs because the cone (section 12) makes
  centering *feel* like it should help; the null result is the lesson.
- **P2, rotated PQ64: up.** A seeded orthogonal rotation before PQ spreads
  the cone's concentrated variance across all 64 subspaces (the poor man's
  OPQ). Registered expectation: recall@10 >= 0.25 at the same 64 bytes.
- **P3, PQ128: up substantially.** 8-dim cells, twice the bytes.
  Registered expectation: recall@10 >= 0.45 at 128 bytes.
- **P4, IVF-1024:** recall@10 >= 0.90 reachable while scanning <= 5% of the
  corpus, at a single-query latency under rung 1's 31.7s by an order of
  magnitude. Control: coarse k-means list sizes on the real geometry are
  more skewed than on an isotropic control at matched n and nlist (the
  cone's tax on every inverted index), measured as Gini.
- **P5, hnswlib reference:** the full corpus cannot load — 10M x 1024 f32
  is 39GB against a 16GB machine, so the library that "just works" never
  gets to run at scale; that arithmetic is the finding. At 1M vectors it
  should deliver p50 under 5ms at recall >= 0.90 at some efSearch — the
  reference point the ladder is climbing toward.
- **P6, Rust kernel:** the int8 sweep spends its 32s converting int8 to
  f32 for numpy's matmul; an i8-native dot kernel (LLVM/NEON, verified
  10/10 against the numpy path before this registration) should finish a
  single 10M query in under 10s warm. The PQ ADC gather should beat
  numpy's 2.4s to under 1s. Query-side quantization (symmetric /127) is
  the kernel's one extra approximation and is disclosed.

Recall sweeps stay on the same 1,000 referee queries; latency samples stay
single-query — every number comparable to weekend 1's. Results follow
below this line only after the runs.
