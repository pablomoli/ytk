# Encoder audit — report 0: baseline corpus characterization

2026-07-16 · issue #73 · local measurements (no web claims in this report)

## Current stack

| Layer | Value |
|---|---|
| Text encoder | `thenlper/gte-small` (384-dim, 512-token window), via Chroma `SentenceTransformerEmbeddingFunction` (`ytk/store.py:50`) |
| Prior encoder | `all-MiniLM-L6-v2`, migrated 2026-07-05 via `experiments/migrate_embedder.py` (precedent + tooling exist) |
| Image encoder | SigLIP-2, precomputed in `ytk.visual`, no embedding function attached — disjoint space from text |
| Store | ChromaDB persistent client at `~/.ytk/chroma` |
| Hardware | Apple Silicon M3, 16 GB RAM — re-embed jobs share the machine with the hub |

## Vector inventory (live counts)

| Collection | Vectors | Notes |
|---|---|---|
| ytk_memories | 4,521 | memory atoms + memos + vault notes |
| ytk_segments | 2,996 | 60-second transcript blocks |
| ytk_videos | 315 | video-level parts (see below) |
| ytk_visual_pending | 761 | SigLIP-2, queue covers |
| ytk_visual | 219 | SigLIP-2, ingested media |
| **Total text vectors** | **7,832** | the full re-embed surface for any migration |

Re-embedding the entire text corpus is a small job by modern standards (~8k short documents); migration cost is dominated by validation, not compute.

## Corpus profile (vault files)

| Bucket | Files | Median chars | p90 | Max |
|---|---|---|---|---|
| sources (videos/reels/articles) | 226 | 5,725 | 47,592 | 136,219 |
| memories (atoms) | 3,516 | 2,325 | 3,419 | 11,874 |
| memos (voice/text) | 23 | 172 | 913 | 1,698 |

Extreme length heterogeneity: three orders of magnitude between a memo and a
long source note. Any chunking/context decision must serve both ends.

## What actually gets embedded

- **Videos** (`store.upsert`): NOT the raw note. Enrichment parts — representative
  vector = thesis+summary under the plain `video_id`; `#c` (key concepts) and
  `#i` (insights+moments) parts prefixed with title+thesis as situating context
  (contextual-retrieval style), collapsed by video_id at query time. This design
  exists precisely because gte-small hard-truncates at 512 tokens (2026-07
  enrichment audit).
- **Segments** (`ytk_segments`): raw transcript joined into ~60 s blocks.
- **Memories/docs** (`upsert_doc` -> `upsert_memory`): one document, truncated
  to `text[:8000]` chars.

## Defects found during baseline (fix before eval)

1. **Silent tail loss on memories.** The 8,000-char cap in `upsert_doc` is
   illusory: gte-small's tokenizer truncates at 512 tokens (~2,000 English
   chars). Memory atoms run median 2,325 / p90 3,419 chars — a large fraction
   of the memories collection embeds only its head. The parts strategy fixed
   this for videos but was never applied to memories. Any eval of "encoder
   quality" on memories currently measures the first ~40% of each note.
2. **Vector/file drift.** ytk_memories holds 4,521 vectors vs ~3,539 candidate
   files (memories + memos) — consistent with #71's phantom double-indexing
   (168 known) plus additional unexplained excess; ytk_videos holds 315 part
   vectors vs 226 source notes (expected: parts multiply per video, but the
   note/video correspondence should be reconciled). Eval numbers on a
   contaminated corpus are meaningless; #71 is a hard prerequisite.

## Constraints this imposes on candidate models

- Must run under sentence-transformers (or a Chroma-compatible wrapper) on MPS,
  comfortably within 16 GB alongside the hub — sub-1B parameters strongly
  preferred.
- A longer context window (2k-8k tokens) would let memories embed whole and
  would simplify (not eliminate) the video parts strategy — weight this
  heavily; it addresses defect 1 structurally.
- 384-dim is the incumbent; higher dims (768/1024) raise Chroma storage and
  UMAP fit cost trivially at this corpus size — dims are not a real constraint.
  Matryoshka-native models would let the visualizations consume cheap 64-128d
  prefixes (pass B question 3).
- Theme identity across snapshots (#83 interest market) and grove/map cached
  topology mean any migration reprices history: migration day must include
  re-fitting the map's UMAP params and re-running grove gates in one stamped
  pass (lesson: engine change = whole grid reruns under one version).

## What the eval harness must include (draft, refined by pass B)

1. Corpus hygiene gate: #71 fixed, vector/file reconciliation clean.
2. Known-item retrieval: LLM-generated "half-remembered" queries against held
   notes ("how did that guy use the television CLI?" style), hit@k per bucket
   (videos / segments / memories).
3. Geometry stability: triplet agreement and neighborhood preservation between
   incumbent and candidate spaces, 20+ seeds, paired intervals — never flat ARI.
4. Truncation sensitivity: same eval with memories embedded whole (parts or
   long-context) vs head-only, to size defect 1's real damage.
5. Throughput: wall-clock to re-embed 7,832 docs on M3/MPS per candidate.
