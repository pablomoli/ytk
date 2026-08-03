# Rank metrics, Phase A — the night the null models won

Pre-registered in `../18-sae-fingerprints/preregistration.md` (section 19 +
18.4b). Six metrics over the fresh Qwen snapshot, three tasks with ground
truth, strictly offline. Production search was never touched. Results
verbatim against registration; three of four predictions failed, each
informatively.

## 19.1 — tag-match@10: FAILED, and the failure is the finding

Registered: Spearman and L1 beat raw cosine by >= 2 points absolute
(prediction derived from arXiv 2606.29571's anisotropy regime split, given
this space's ‖mean‖ = 0.51). Measured (% of top-10 neighbors sharing a
tag; permuted floor 41.4):

| metric | raw | centred |
|---|---|---|
| cosine | 82.0 | **83.3** |
| L1 | 81.9 | — |
| Spearman | 81.7 | 82.9 |
| CSLS(10) | 82.6 | — |

Rank metrics do not beat cosine here — they lose slightly. The
anisotropy-decides regime split did not replicate on this corpus/task:
Qwen3's cone, though geometrically strong, is apparently not the
pathological concentration the paper's losing encoders have. The only
gain anywhere is centring (+1.2), consistent with the open
centring-helps-search thread — but under the registered Phase B gate
(**a >= 2-point win by a non-cosine metric**), nothing qualifies.

**Phase B verdict, decided by pre-registration: not earned. Production
search stays cosine.** The centring question remains open and belongs to
the eval gate on its own merits, not through this door.

## 19.2 — CSLS hub flattening: SPLIT

Registered: top-10 answerer share cut >= 1/3, median min-support shift
< 0.01. Measured: share 12.2% -> 6.3% (a 48% cut — the flattening works,
fig 02 left) but the median min-support shift is -0.0119, just past the
registered tolerance. Half confirmed, half failed; reported as split. If
the path interface ever wants CSLS's diversity, it buys it at ~0.012
median support — a price now known, not assumed.

## 19.3 — duplicate detection: FAILED via a wrong assumption

Registered: the known duplicate pair ranks strictly higher under CSLS
than cosine. Measured: rank 2 under every metric, no movement possible in
either direction — and rank 1 for the heatmap note belongs to a
*different* note (the y7 fMRI reel, cos 0.673) that beats the duplicate
(0.630). The assumption was wrong: this corpus's "duplicates" are
re-ingestions with different enrichment texts, not near-identical
vectors. Consequence, already applied in the road scripts: dedup must use
content identity (shortcode markers), never embedding proximity.

## 18.4b — continuous cross-space agreement: bar cleared, control collapsed

Registered: differential-z cosine (SAE) vs centroid cosine (Qwen) at
r >= 0.4, with shuffled labels expected near 0. Measured: r = 0.832 —
and shuffled labels give r = 0.757. The control expectation was wrong
about the null: tag z-vectors share corpus-level structure whatever the
labels say, and both spaces inherit it, so almost all of the correlation
is scaffolding, not tag identity. The tag-specific excess (0.832 vs
0.757) is real but small. **Interpretation withdrawn**: no cross-space
tag-structure claim survives this null. The 18.4 quantized-Jaccard
failure was not merely quantization. (Fig 03 is titled accordingly.)
Echoes the standing rule: new metrics need their own nulls, measured,
never assumed.

## Figures

- `01-tag-match.png` — six metrics against the permuted floor
- `02-hub-flattening.png` — CSLS concentration curve + the support price
- `03-continuous-overlap.png` — the r=0.83 that the shuffle takes back

## Render

```bash
uv run --with matplotlib python scripts/rank_metrics.py
```
