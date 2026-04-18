---
title: "Session 006 — graphify Integration"
date: 2026-04-18
tags:
  - ytk
  - session-brief
---

## What Was Built

Three features adopted from graphify (safishamsi/graphify) as native ytk implementations — no graphifyy package dependency.

### Feature 1: Whisper Transcription Tier

`ytk/transcript.py` rewritten. Old chain: youtube-transcript-api → yt-dlp (.vtt) → error. New chain: youtube-transcript-api → faster-whisper (local ASR) → error.

- yt-dlp subtitle tier removed (same data source as tier 1, negligible added coverage)
- `_download_audio(url)` caches audio in `~/.ytk/audio/` by URL SHA1 hash
- `_fetch_via_whisper()` preserves `seg.start`/`seg.end` timestamps — key_moments enrichment works normally
- `whisper_model: str = "base"` added to `Config` (`ytk/config.py`), configurable in `~/.ytk/config.yaml`
- `fetch_transcript(url, whisper_model=...)` signature propagated to CLI and scheduler callers
- Exception narrowed to `(NoTranscriptFound, TranscriptsDisabled)` to avoid triggering expensive Whisper download on network errors

### Feature 2: SHA256 Incremental Cache

`ytk/cache.py` (new file):
- `file_hash(path)` — SHA256 of body with YAML frontmatter stripped (so metadata-only edits don't trigger re-embedding)
- `load_index_cache() / save_index_cache()` — `~/.ytk/index_cache.json`, atomic write via `os.replace`
- `update_cache_entry(path, cache)` — hash and record in dict

`ytk/vault.py` — `reindex_vault(force=False)`:
- Loads real cache before checking `force` (so stale-deletion works correctly on force runs)
- Skips files whose hash matches; records empty-body files in cache to avoid re-hashing them every run
- Removes stale entries for deleted files before saving
- `force=True` bypasses the hash check but still benefits from stale pruning

`ytk/mcp_server.py`:
- `vault_reindex(force=False)` — `force` parameter exposed to Claude sessions
- `vault_write` — now extracts frontmatter `id:` field for doc_id (matching `reindex_vault` logic) before falling back to path-based ID; prevents ChromaDB duplicates on notes with custom IDs

`ytk/cli.py` — `ytk reindex --force` flag added.

### Feature 3: HTML Knowledge Graph

`ytk/graph.py` (new file):
- `build_graph(threshold=0.75)` — nodes from ChromaDB memories + videos collections; edges from shared tags (EXTRACTED, weight=1.0), shared key_concepts (EXTRACTED, weight=0.9), semantic similarity above threshold (INFERRED, weight=similarity)
- `detect_communities(G)` — graspologic Leiden with networkx greedy_modularity fallback; isolated nodes assigned their own community IDs
- `export_html(G, output)` — self-contained vis.js HTML; nodes sized by degree, colored by community; click opens source URL; creates parent dirs before writing
- `export_json(G, output)` — `{nodes, edges}` JSON for programmatic querying

`ytk/cli.py` — `ytk graph --open --output PATH --threshold FLOAT` command.

**Known limitation:** Semantic edges are queried within each ChromaDB collection separately. Cross-collection memory↔video semantic edges require a combined collection or separate query+merge step; tag and concept edges already bridge collections.

## Test Suite

22 tests across 5 test files, all passing:
- `tests/test_config.py` (2) — whisper_model default and YAML loading
- `tests/test_transcript.py` (3) — timestamps preserved, fallback triggered, no yt-dlp subtitle tier
- `tests/test_cache.py` (6) — frontmatter stripping, hash changes, roundtrip, missing cache, update entry
- `tests/test_reindex_cache.py` (3) — skip cached, embed stale, force bypasses cache
- `tests/test_graph.py` (8) — nodes, tag edges, concept edges (real files), semantic threshold, community detection, JSON/HTML export

## Key Decisions

- **No graphifyy dependency** — graphifyy's base install includes 25 tree-sitter parsers; its `transcribe()` discards timestamps; its cache stores graph nodes/edges not ChromaDB index state. Native implementations are cleaner for all three features.
- **Removed yt-dlp subtitle tier** — tier 1 (youtube-transcript-api) and old tier 2 (yt-dlp .vtt) both fetch YouTube's pre-built caption data; coverage is nearly identical. Whisper covers the genuinely uncaptioned case.
- **Frontmatter stripped before hashing** — vault note frontmatter changes frequently (dates, tags); stripping avoids spurious re-embedding on metadata-only edits.
- **Cache loaded before force check** — initializing cache to `{}` on `force=True` would make stale-deletion a no-op and produce an incomplete cache after the run.
- **doc_id extraction aligned** — `vault_write` and `reindex_vault` now use the same frontmatter `id:` extraction logic to prevent duplicate ChromaDB records.

## Commands

```bash
# Run tests
uv run pytest tests/ -v

# Whisper fallback (automatic when YouTube has no captions)
ytk add <url>

# Incremental reindex
ytk reindex

# Full reindex (ignores cache)
ytk reindex --force

# Build knowledge graph
ytk graph --open --threshold 0.75

# MCP: force reindex from Claude session
# vault_reindex(force=True)
```

## What's Next

- Phase 6 — Local UI (TanStack Start): transcript viewer, vault browser
- Phase 7 — iMessage capture pipeline
