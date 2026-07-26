# ytk — Session 044 Brief

**Date:** 2026-07-26
**Mode:** Permanent Chroma server migration and visual-index recovery

## Outcome

The permanent repair for issue #130 is live. One launchd-managed Chroma server
now owns the active database at `~/.ytk/chroma-server` and listens only on
`127.0.0.1:8000`. The hub, CLI, MCP server, schedules, and scripts use
`chromadb.HttpClient` through `CHROMA_URL`; they no longer open the active
SQLite/HNSW files with independent `PersistentClient` instances.

The hub is responsive on `127.0.0.1:6969`, text search is ready, ingestion is
idle, and visual search is enabled again. The damaged legacy visual collections
were not copied. They were rebuilt from source covers into clean collections:

- `ytk_visual`: 423 saved covers
- `ytk_visual_pending`: 1,397 pending covers

The legacy store at `~/.ytk/chroma` remains untouched and has no open process
holders.

## Changes

- Added a shared Chroma runtime boundary that selects an HTTP client when
  `CHROMA_URL` is set and preserves the embedded client only for legacy or
  isolated operation.
- Added loopback-only URL validation so the local database cannot accidentally
  be exposed to the network.
- Added `ytk chroma serve`, `install`, `migrate`, `restart`, `status`, and
  `uninstall` commands with launchd management and readiness checks.
- Added a batch migration path that preserves IDs, documents, metadata,
  embeddings, collection metadata, and Chroma collection configuration.
- Routed store and script callers through the shared runtime instead of direct
  embedded clients.
- Added `ytk visual rebuild --yes`, which replaces only the two exact visual
  collections and reconstructs them from source covers.
- Kept the visual circuit breaker as defense in depth; a damaged visual
  collection can still degrade to empty results without freezing the hub.
- Pinned ChromaDB 1.5.9 and added isolated server integration tests.

Relevant commits on `master`:

- `58c38ae` — permanent server migration merged to local master and pushed
- `0f6db25` — preserve collection configuration during migration

Design and execution documents:

- `docs/superpowers/specs/2026-07-26-chroma-server-migration-design.md`
- `docs/superpowers/plans/2026-07-26-chroma-server-migration.md`

## Migration Incident and Correction

The first fresh migration exposed a collection-configuration bug before the
hub was cut over: the copied collections were created with Chroma defaults
rather than the source HNSW configuration, so the registered
`InstructionAwareEF` rejected them as incompatible.

The hub was immediately rolled back to the untouched legacy store. The
migration now passes each source collection's public `configuration` into
target creation, and `InstructionAwareEF` is registered with Chroma's embedding
function registry. A regression test covers the client-supplied embedding
function compatibility path. The invalid first target was retained at:

`~/.ytk/recovery/chroma-server-invalid-config-20260726-134842`

## Verified Data

The completed migration report is
`~/.ytk/recovery/chroma-migration.json`. Independent source-versus-target
counts matched:

| Collection | Count |
|---|---:|
| `ytk_memories` | 6,801 |
| `ytk_memories_v2` | 4,531 |
| `ytk_segments` | 2,996 |
| `ytk_segments_v2` | 5,656 |
| `ytk_videos` | 316 |
| `ytk_videos_v2` | 200 |

Only the Chroma server process holds
`~/.ytk/chroma-server/chroma.sqlite3`. No process holds the legacy
`~/.ytk/chroma/chroma.sqlite3`.

## Verification

```text
Ruff                               clean
Pyright                            0 errors
Full Python suite                  851 passed, 1 deselected
Retrieval hit@1                    0.712, delta +0.000
Retrieval hit@5                    0.904, delta +0.000
Retrieval hit@10                   0.942, delta +0.000
Three concurrent HTTP clients      healthy
Live /api/ready                    search=true
Live /api/ingest/status            running=false, queued=[]
Representative visual query       relevant astronomy results
Repository                         master matches origin/master
```

## Recovery Material

- Pre-cutover runtime backup:
  `~/.ytk/recovery/chroma-cutover-20260726-133900`
- Migration report:
  `~/.ytk/recovery/chroma-migration.json`
- Rejected first target:
  `~/.ytk/recovery/chroma-server-invalid-config-20260726-134842`
- Untouched legacy database:
  `~/.ytk/chroma`

## Architectural Follow-Ups

`ytk_visual` is a Chroma collection of vectors, not the SigLIP encoder itself.
The system already uses it for similar-note recommendations, inbox visual
search, pending-item search, MCP visual search, map/profile analysis, and
ingest-time cover indexing. Enrichment receives the actual sampled frames or
slides directly, which contain richer information than a visual vector.

A future experiment can add optional visual retrieval to enrichment: embed the
incoming cover or frames, fetch a small set of visually related saved items,
and supply their bounded metadata as user-history context. This must be
evaluated before adoption because cover similarity can introduce misleading
context or reinforce superficial visual motifs.

Port 8000 is loopback-only and operationally safe, but it is a common local
development default. A proposed organizational follow-up is to group ytk
services at 6969 for the hub, 6970 for Chroma, and reserve 6971–6979 for ytk
workers and scratch servers. A fixed range improves ownership clarity but
cannot guarantee collision freedom; startup must still identify and report an
existing listener.

## Commands

```bash
ytk chroma status
curl --max-time 10 -fsS http://127.0.0.1:6969/api/ready
curl --max-time 10 -fsS http://127.0.0.1:6969/api/ingest/status
ytk search "chroma server migration"
ytk visual similar --text "astronomy and real star clusters"
uv run pytest -q
uv run ytk eval
gh issue view 130
```
