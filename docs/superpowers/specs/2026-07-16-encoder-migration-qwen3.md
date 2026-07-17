# Spec: encoder migration to Qwen3-Embedding-0.6B @ 1024d

2026-07-16 · owner: ytk core · evidence: docs/research/encoder-audit/ reports 0-5
Status: approved-pending-preflight (two cheap checks below)

## Decision

Migrate ytk's text encoder from thenlper/gte-small (384d, 512-token window)
to Qwen/Qwen3-Embedding-0.6B at **native 1024 dims, whole-document embedding
(no parts)**. Verdict from the measured gates (report 5, 156 known-item
queries, paired bootstrap):

| Gate | Result |
|---|---|
| Retrieval | hit@5 0.859 → 0.923 (+6.5pt, CI [+2.6, +10.9]); segments 0.841 → 0.977 |
| Geometry | triplet agreement 0.758 → 0.855 (+9.7pt, CI excludes zero) |
| Operational | ~65 min one-time re-embed, 2.8 GB peak, ~1 s/vector ongoing |

Explicitly rejected by the evidence: bge-small (geometry regression), the
384d MRL drop-in (retrieval gain loses significance), and porting the parts
strategy (native whole-doc beats it at 1/3 the encode cost). Dropping parts
resolves #84's failure class structurally.

## Phase 0 — Pre-flight (blocks everything; ~1 evening)

1. **Query validity check.** Hand-verify 20 random queries from
   `data/queries.jsonl` against their gold docs; replay any real search
   strings we can recover from hub usage. Abort criterion: if the synthetic
   queries look unlike real usage, rebuild the query set before trusting
   Gate 1.
2. **Interactive latency bench.** Measure single-short-text encode (warm
   model) on MPS: target < 500 ms for /search and hub queries. Also measure
   cold-start (model load 1.4 s + first encode) since the hub loads lazily.
3. **MLX runtime spike (recommended, can run parallel to 1-2).** Bench
   mlx-embeddings' Qwen3-0.6B on the same corpus sample; accept only if
   per-vector cosine agreement with the PyTorch reference > 0.999. If MLX
   is >= 3x faster, it becomes the serving path and step 2's targets are
   re-measured there. If latency in step 2 already passes, MLX is an
   optimization track, not a blocker.

## Phase 1 — Code changes (before migration day)

- **New collections, not in-place**: Chroma collections are dim-fixed.
  Create `ytk_memories_v2`, `ytk_videos_v2`, `ytk_segments_v2` at 1024d;
  keep v1 untouched for rollback. Collection names resolve through one
  constant so the cutover is a single switch.
- **Custom embedding function** replacing the stock
  SentenceTransformerEmbeddingFunction: Qwen3 is instruction-aware — 
  documents embed plain, queries embed with the retrieval instruction
  prefix. Chroma's EF protocol only exposes one call path, so search
  functions embed queries explicitly and pass `query_embeddings` (not
  `query_texts`). Prefix-free embeddings remain available for clustering
  consumers if a later experiment wants them.
- **Simplify upsert paths**: whole-doc embedding, `text[:8000]` cap stays.
  KEEP the #71 phantom guard (id/source_path dedupe on upsert) — it is
  independent of chunking. `_split_doc` and video parts remain only until
  cutover, then the parts branch is deleted; consumer `"#" in id` filters
  are harmless and stay for one release.
- **Migration script**: extend `experiments/migrate_embedder.py` — read v1
  docs + metadata, re-embed whole docs, write v2 with metadata copied
  verbatim (ingested_at preservation, grove v6 finding 15). Idempotent,
  resumable, logs to /tmp/ytk-encoder-eval.log style.

## Phase 2 — Migration day (one stamped pass, ~2 h)

Protocol (report 4 rule: never let two geometries coexist silently):

1. Stop the hub (`launchctl bootout gui/501/com.ytk.hub` — remember: reinstall
   does NOT restart it; check /api/ingest/status is idle first).
2. Run the migration script → v2 collections (est. 65-90 min on MPS, or
   faster via MLX if Phase 0.3 adopted it).
3. Verify: v2 counts == v1 doc counts (no parts multiplier), zero phantom
   families (dedupe script re-run), spot-search 10 known items.
4. Flip the collection constant; run the full test suite.
5. Re-fit downstream geometry in the same pass, stamped with the same
   commit: rebuild map (new fitted UMAP params), re-run grove gates
   (triplet agreement vs authored buckets; this is a legitimate
   "engine change" epoch — grove topology re-attaches against the new
   space, growth animations reset from a new baseline snapshot).
6. Interest snapshots (#83 dependency): freeze a pre-migration snapshot,
   then pin theme identity across the swap via theme-centroid matching
   (TTEC-style compass is the fallback if matching is ambiguous).
7. Rebuild web bundles, reinstall (`uv tool install --reinstall .`),
   restart hub (`launchctl kickstart -k gui/501/com.ytk.hub`), verify
   /fresh, /search, /map render.
8. Commit everything as one stamped change; push. v1 collections are
   deleted only after a week of daily use without regression reports.

## Phase 3 — Post-migration

- Watch ingest latency for a week (each video now adds ~1 min of encode in
  the background job; acceptable per Gate 3, but verify no queue backup).
- Carry-forward experiments from the audit: Procrustes stability across
  re-embeds, UMAP faithfulness per input dim (1024 vs truncations) before
  the galaxy (#78) fits its geometry, and the interest-market (#83) builds
  on the new snapshot epoch.
- Revisit EmbeddingGemma / gte-modernbert only if Qwen3's operational cost
  becomes a real pain — the quality bar they must beat is now measured.

## Rollback

Flip the collection constant back to v1 (kept intact through Phase 2), 
revert the EF commit, restart hub. Cost: minutes. The stamped-epoch rule
means map/grove artifacts from the v2 window are regenerated on rollback
too — never mix.

## Non-goals

- No cloud embedding APIs (local-first is validated by the competitive
  field and is a project invariant).
- No text/image space unification — SigLIP-2 stays disjoint (no verified
  evidence unification helps; revisit only with a measured reason).
- No schema-preserving 384d shortcut — measured as not clearing Gate 1.

## Traceability

- Evidence: docs/research/encoder-audit/00..05 (3-pass web research, 309
  agents, 75 verified claims; local harness: 6 spaces, 156 queries, 25-seed
  paired geometry).
- Fixes shipped en route: #71 (phantom vectors, guard + cleanup),
  #84 (memory truncation, parts interim fix — superseded by this migration).
- Issues: #73 (this decision), #83 (consumes the snapshot-epoch protocol),
  #82 (MLX spike doubles as mobile-path research).
