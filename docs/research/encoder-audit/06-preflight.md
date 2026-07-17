# 06 — Phase 0 pre-flight results

2026-07-16 (late) · spec: `docs/superpowers/specs/2026-07-16-encoder-migration-qwen3.md`
Scripts: `experiments/encoder_harness/bench_latency.py`, `experiments/encoder_harness/mlx_agreement.py`
Raw reports: `data/latency.bench.json`, `data/mlx_agreement.json` (gitignored with the rest of `data/`)

## 0.1 Query validity spot-check — PASS (20/20)

Sampled 20 of 156 queries (`random.seed(73)`) from `data/queries.jsonl` and
verified each against its gold doc's full text. All 20 are valid known-item
queries: every one names specifics (tool names, bug symptoms, scene details)
that appear in — and are distinctive to — the gold doc. Two required reading
past the doc's opening to confirm and both held:

- "calendar layout to start on Sunday instead of Monday" → gold is a sprint
  session whose body contains the issue #110 fix (DAY_NAMES, getDay() offset).
- "amateur... on-the-nose therapy exposition" → segment contains the therapy
  scene critique and the word "amateur" verbatim.

Bucket mix of the sample (12 memories / 5 segments / 3 videos) tracks the
corpus mix. Style is recall-shaped ("that session where...", "how did that
guy..."), which matches ytk's stated use case.

Caveats, both acceptable:

- **No real queries exist to replay.** The hub does not log search strings
  anywhere (checked `ytk/ui/hub.py`, `~/.ytk/*.log`, `ytk.db` — only a
  `videos` table). Recommendation: log hub /search queries going forward so
  the next eval can use real traffic. Filed as a post-migration note.
- Some memory-bucket queries are more informative than a human would type
  (e.g. full root-cause phrasing). This inflates absolute hit@5 for all
  models symmetrically; the migration decision rests on the paired delta,
  which is robust to it.

Abort criterion (queries unlike real usage) not triggered. Gate 1 stands.

## 0.2 Interactive latency — PASS

Qwen3-Embedding-0.6B, fp16, max_seq 3072, MPS, sentence-transformers.
Single-text encodes, production query path (retrieval instruction prefix):

| Measurement | Result | Target |
|---|---|---|
| Warm query (prefixed) | median 139 ms, p95 216 ms | < 500 ms — PASS |
| Warm query (plain) | median 106 ms, p95 333 ms | — |
| Warm doc (median length, ~2k chars) | median 653 ms | consistent with Gate 3's ~1 s/vector |
| Cold start | 6.7 s load + 0.7 s first encode = 7.4 s | — |

Two Phase 1 consequences:

- **Cold start is 7.4 s, not the ~1.4 s the audit estimated** (that number
  was a warm-cache reload). The hub loads the model lazily, so the first
  search after a hub restart would hang ~8 s. Phase 1 should eager-load the
  encoder on hub start (background thread at startup), not on first query.
- Warm latency leaves ample headroom; no need to gate the migration on MLX.

## 0.3 MLX runtime spike

`mlx-embeddings` 0.1.0 supports the qwen3 architecture and loads
`Qwen/Qwen3-Embedding-0.6B` weights directly (no mlx-community conversion
needed). Acceptance: per-vector cosine vs the PyTorch reference > 0.999 on
100 docs; adoption as serving path requires >= 3x PyTorch's 2.0 vectors/s.
Batch=8 output is additionally checked against batch=1 to validate padded
last-token pooling.

| Measurement | Result | Bar |
|---|---|---|
| Cosine vs PyTorch (100 docs, batch=1) | min 0.99981, mean 0.99988, 100% > 0.999 | > 0.999 — PASS |
| Batch=8 vs batch=1 min cosine | 0.99972 | pooling handles padding correctly |
| Bulk throughput | 3.2 vec/s (batch=1), 2.1 vec/s (batch=8) | >= 6.0 (3x) — FAIL |
| Warm prefixed query | median 75.8 ms | 1.8x faster than PyTorch's 139 ms |

Batching makes MLX *slower*: padding to the longest doc in each batch burns
compute on pad tokens (no sequence packing in mlx-embeddings 0.1.0). So MLX
does not become the bulk re-embed path. It is numerically trustworthy and
~2x faster on single short texts, which makes it a clean future optimization
for the hub's interactive query path (relevant to #82) — optional, post-
migration, and only worth it with an agreement re-check pinned in CI-style
before any swap.

## Verdict

All three pre-flight checks pass; the spec's abort criteria were not
triggered. **Phase 1 is unblocked** with sentence-transformers (fp16,
max_seq 3072) as both the migration and serving runtime.

Carried into Phase 1:

1. Eager-load the encoder at hub startup (cold start is 7.4 s, lazy load
   would hang the first search).
2. Log hub search queries so the next eval has real traffic to replay.
3. MLX interactive-path swap stays parked as an optimization (#82).
