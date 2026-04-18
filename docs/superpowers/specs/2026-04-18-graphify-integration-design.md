# graphify Integration Design

**Date:** 2026-04-18
**Status:** approved
**Scope:** Three improvements adopted from graphify's patterns, implemented natively in ytk (no graphifyy package dependency)

---

## Background

graphify (safishamsi/graphify, ~30k stars) is a knowledge graph builder for code and media. ytk and graphify overlap in three areas where graphify's approach is better than ytk's current implementation:

1. Transcript fallback coverage — graphify uses faster-whisper as a local ASR fallback
2. Incremental vault reindexing — graphify uses SHA256 per-file hashing to skip unchanged files
3. Knowledge graph visualization — graphify builds interactive HTML graphs from document collections

ytk adopts these patterns without taking graphifyy as a dependency. The rationale: graphifyy's base install includes 25 tree-sitter language parsers ytk will never use; graphify's `transcribe()` discards timestamps (ytk needs them for `key_moments`); and graphify's cache format stores graph nodes/edges, not ChromaDB index state. Direct library deps and native implementations are cleaner for all three features.

---

## Feature 1: Whisper Transcription Tier

### Current behavior

```
youtube-transcript-api → yt-dlp (.vtt subtitles) → ERROR
```

Tier 2 (yt-dlp subtitle download) is removed — it covers a narrow edge case (age-gated videos, occasional API divergence) and adds latency for negligible gain. Both tier 1 and the old tier 2 fetch YouTube's pre-built caption data; if YouTube has no captions the video fails regardless.

### New behavior

```
youtube-transcript-api → faster-whisper (local ASR)
```

### Implementation

**`pyproject.toml`** — add `faster-whisper` to dependencies. `yt-dlp` stays — it is still required for audio download in the Whisper tier, just no longer used for subtitle fetching.

**`ytk/config.py`** — add `whisper_model: str = "base"` to the config model. Configurable in `~/.ytk/config.yaml`.

**`ytk/transcript.py`** — changes:
- Remove `_fetch_via_ytdlp()` entirely
- `fetch_transcript()` gains a `config` parameter (passed down from CLI/scheduler callers that already hold a `Config` instance) and threads it to `_fetch_via_whisper`. No other tier needs config today.
- Add `_fetch_via_whisper(url: str, config: Config) -> tuple[list[dict], str]`:
  - Downloads audio-only stream via yt-dlp into `~/.ytk/audio/`. Filename is `yt_{sha1_of_url[:12]}.{ext}` — reuses cached audio on re-runs.
  - Runs `WhisperModel(config.whisper_model).transcribe()` with `word_timestamps=False`
  - faster-whisper segments have `.start`/`.end` attributes — converts to `{start, duration, text}` preserving timestamps
  - Returns source label `"whisper"` so vault note frontmatter records which tier was used
- Update `fetch_transcript()`: tier 1 → tier 2 (Whisper) → raise

### Configuration

```yaml
# ~/.ytk/config.yaml
whisper_model: base   # base | small | medium | large
```

`base` is the default — fast, adequate for clear English speech. `small` is a reasonable upgrade for technical/accented content. YouTube's auto-captions are higher quality than Whisper base when they exist; Whisper's value is coverage, not accuracy.

---

## Feature 2: SHA256 Incremental Cache

### Current behavior

`ytk reindex` and `vault_reindex` (MCP tool) re-embed every vault file on every run. Full scan, no skip logic.

### New behavior

Files whose content hash matches the cache are skipped. Only new or changed files are embedded.

### Implementation

**`ytk/cache.py`** — new file:
- `file_hash(path: Path) -> str` — SHA256 of file body with YAML frontmatter stripped. Frontmatter is stripped because metadata-only changes (tag edits, date updates) don't affect the embedded content and shouldn't trigger re-indexing.
- `load_index_cache() -> dict[str, str]` — reads `~/.ytk/index_cache.json`, returns `{absolute_path: sha256}`
- `save_index_cache(cache: dict[str, str]) -> None` — writes atomically via temp file + `os.replace()`
- `update_cache_entry(path: Path, cache: dict) -> dict` — hashes file and sets entry; returns updated cache

**`ytk/store.py`** — update `reindex_vault()`:
- Load cache at start
- For each `.md` file found, compute hash and compare to cache
- Skip embedding if hash matches; embed and update cache entry if new or changed
- Remove entries for files that no longer exist (stale cleanup)
- Accept `force: bool = False` param — if True, skip cache check entirely

**`ytk/mcp_server.py`** — update `vault_reindex` tool:
- Pass `force=False` by default
- Expose `force` as an optional tool parameter so Claude can trigger a full rebuild when needed

**`ytk/mcp_server.py`** — update `vault_write` tool:
- After writing and indexing a file, call `update_cache_entry()` so the next `reindex` skips it

**`ytk/cli.py`** — update `reindex` command:
- Add `--force` flag that passes `force=True` to `reindex_vault()`

### Cache location

`~/.ytk/index_cache.json` — simple JSON dict, human-readable, sits alongside `ytk.db` and `chroma/`.

---

## Feature 3: HTML Knowledge Graph

### New behavior

`ytk graph` builds an interactive HTML knowledge graph from all indexed vault notes and opens it in the browser.

### Implementation

**`ytk/graph.py`** — new file:
- `build_graph(threshold: float = 0.75) -> nx.Graph`
  - Loads all indexed vault notes (scan vault dirs for `.md` files)
  - Parses each note's frontmatter (tags) and `## Key Concepts` section (concept names)
  - **Edge tier 1 — shared interest_tags:** draw edge for any two notes sharing a tag. Weight 1.0, type EXTRACTED.
  - **Edge tier 2 — shared key_concept terms:** draw edge for any two notes naming the same concept. Weight 0.9, type EXTRACTED.
  - **Edge tier 3 — ChromaDB semantic similarity:** query each note's top-10 neighbors from ChromaDB, keep pairs above `threshold`. Weight = similarity score, type INFERRED.
  - Node attributes: `title`, `url`, `note_type` (video/web/memory from vault path), `tags`, `community`
- `detect_communities(G: nx.Graph) -> dict[node, int]`
  - Try `graspologic` Leiden algorithm; fall back to `networkx.algorithms.community.greedy_modularity_communities()`. Returns node → community int mapping.
- `export_html(G: nx.Graph, output: Path) -> None`
  - Renders a self-contained HTML file. vis.js loaded from CDN.
  - Nodes sized by degree (high-connectivity notes are larger).
  - Nodes colored by community.
  - Edges colored by type: tag=blue, concept=green, semantic=grey with opacity = weight.
  - Click node → opens source URL in new tab.
- `export_json(G: nx.Graph, output: Path) -> None`
  - Writes `~/.ytk/graph.json` (NetworkX node/edge data) for future CLI querying.

**`ytk/cli.py`** — add `ytk graph` command:
```
ytk graph [--open] [--output PATH] [--threshold FLOAT]
```
- `--open` — opens `graph.html` in browser after generation (via `webbrowser.open()`)
- `--output` — override default output path (`~/.ytk/graph.html`)
- `--threshold` — semantic similarity cutoff (default 0.75)
- Prints node count, edge count, community count on completion

**`pyproject.toml`** — add `networkx` to base dependencies. Add optional `graspologic` dep:
```toml
[project.optional-dependencies]
graph = ["graspologic"]
```

### Output files

| File | Contents |
|---|---|
| `~/.ytk/graph.html` | Interactive vis.js visualization, self-contained |
| `~/.ytk/graph.json` | Raw graph data for programmatic querying |

---

## Files Changed

| File | Change |
|---|---|
| `pyproject.toml` | + `faster-whisper`, + `networkx`; optional `graspologic` |
| `ytk/transcript.py` | Remove `_fetch_via_ytdlp()`; add `_fetch_via_whisper()` |
| `ytk/config.py` | + `whisper_model: str = "base"` |
| `ytk/cache.py` | NEW |
| `ytk/store.py` | Update `reindex_vault()` to use cache |
| `ytk/mcp_server.py` | Update `vault_reindex` + `vault_write` tools |
| `ytk/cli.py` | + `ytk graph` command; + `--force` on `reindex` |
| `ytk/graph.py` | NEW |

---

## What Is Not Changed

- ChromaDB remains the search backend — the graph is a visualization layer on top, not a replacement.
- `vault_write` auto-indexing behavior is unchanged; the cache update is additive.
- Enrichment pipeline (Haiku, interest tags, key moments) is unchanged.
- Playlist scheduler is unchanged.
- `ytk ingest`, `ytk remember`, `ytk gc` are unchanged.
