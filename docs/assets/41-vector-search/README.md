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

---

## Results: two hits, three misses, one split — and every miss has a mechanism

**P1 hit — centering is a no-op, exactly as registered** (figure 05).
Centered PQ64: recall@10 0.1573 vs raw 0.161, inside the ±0.02 band, at the
same 2.24s. K-means moved its centroids with the data; the constant q·mu
never had a vote.

**P2 miss — a random rotation is also a no-op: 0.156 vs the 0.25 bar.**
The registered mechanism was wrong, and the autopsy is the lesson: a random
rotation only helps when variance is piled into specific *coordinate*
slices, but the cone is a direction with no reason to align with Qwen's
axes — relative to the corpus's principal axes the raw coordinate basis
already is a random basis, and rotating a rotationally symmetric situation
changes nothing in expectation. OPQ earns its improvement by *fitting* a
variance-balancing rotation; the poor man's version was too poor to be OPQ
at all.

**P3 miss — capacity scales but the bar overshot: PQ128 0.337 vs 0.45.**
Doubling the bytes doubled the truth kept (0.161 -> 0.337, 4.33s, 1.19GB).
The clean reading across rung 3: at this geometry no cheap transform and no
doubling of PQ capacity buys retrieval-grade recall — compressed codes are
a candidate generator, not an answer, which is exactly why production
systems staple a rerank stage on top of them.

**P4 split — the curve never reaches the box, and the control lands**
(figure 06). IVF-1024 climbs 0.10 -> 0.83 as nprobe doubles 1 -> 64, but
0.90-inside-5% is unreachable: nprobe 64 scans 6.6% for 0.826. The control
clause hit: real-geometry list sizes carry ten times the isotropic skew
(Gini 0.091 vs 0.009) — the cone's tax on every inverted index, though at
this magnitude skew alone does not explain the flat curve; true-neighbor
smear across lists is the stated hypothesis, unmeasured here. The latency
column (8ms at nprobe 2, 1.04s at 64) still pays numpy's int8->f32
conversion tax — the curve's shape is the index's, the milliseconds are
the interpreter's.

**P5 miss — the reference is fast and wrong** (figure 07). The registered
finding stands (39GB never loads on 16GB; the footprint bars are the
figure), and at 1M hnswlib is as fast as promised: 0.5-5.2ms p50. But
recall tops out at 0.602 at ef 200 against the predicted 0.90 — on this
unit-norm, cone-bearing, hub-heavy geometry the graph index is not a
solved problem either, at any ef in the grid. RSS 7.9GB includes the
subset ground-truth pass, disclosed rather than restated as the index's
own footprint.

**P6 pass, both targets** (figure 08, the CYAN points). The i8-native
sweep: 5.81s p50 threaded (single-thread 20.7s reported beside it) vs
numpy's 31.7s and the 10s bar — 1.6GB/s effective against numpy's 0.3.
The ADC gather: 0.318s steady-state vs 2.4s and the 1s bar. Ground-truth
overlap 29/30 across spot checks, so the kernel's one extra approximation
(query quantized symmetric /127) costs a rounding error. Both benches ran
after the queue finished, machine exclusive; the corpus was partially
page-cached, as numpy's references were.

The scoreboard the section keeps: P1 and P6 hit, P2, P3 and P5 missed,
P4 split. Three of the six numbers this weekend registered were wrong in
the honest direction — the geometry is harder than the intuition, at
every rung, and the record says so at the same prominence as the wins.

## Figures

- `01-the-baseline.png` — 18k vectors: exact brute force beats the index.
- `02-the-impostor-corpus.png` — the synthetic 10M wears the real geometry.
- `03-the-wall.png` — exact at 10M: the cliff is the disk.
- `04-what-speed-costs.png` — weekend 1's ladder: int8 and PQ64 priced.
- `05-the-byte-budget.png` — rung 3: predictions drawn, dots land or miss.
- `06-the-inverted-index.png` — rung 4: the scan-fraction curve and the
  cone's tax.
- `07-the-reference.png` — rung 5: what fits, and the 1M curve.
- `08-the-climb.png` — every operating point on one recall-latency map.

Sidecars `rung0.json`-`rung6.json`, `ivf-control.json`, `baseline.json`,
`match.json`; runner `scripts/e41_vector_search.py` (figures via
`figures2`); kernel `experiments/e41_kernel/`.
