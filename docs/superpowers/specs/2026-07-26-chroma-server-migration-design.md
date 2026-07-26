# Chroma Server Migration Design

**Date:** 2026-07-26  
**Issue:** #130  
**Status:** Approved

## Problem

ytk currently creates a `chromadb.PersistentClient` inside every process that
uses search or indexing. In normal operation that includes the hub, one or more
MCP servers, CLI commands, scheduled jobs, and map/deduplication scripts. All of
those processes open the same `~/.ytk/chroma` SQLite and HNSW files.

Chroma supports concurrent threads inside one process, but it does not support
concurrent writers from multiple processes sharing a persistence path. The
current topology therefore violates Chroma's operating constraints.

The immediate incident also left `ytk_visual` with a damaged HNSW segment.
Calling `count()` on that collection blocks in Chroma's Rust binding while
holding the Python GIL. The visual circuit breaker keeps the hub responsive,
but the damaged data and unsupported storage topology remain.

## Current Data

The embedded store is 398 MB and contains eight collections:

| Collection | Dimension | Rows | Disposition |
|---|---:|---:|---|
| `ytk_memories` | 384 | 6,799 | copy |
| `ytk_memories_v2` | 1,024 | 4,531 | copy |
| `ytk_segments` | 384 | 2,996 | copy |
| `ytk_segments_v2` | 1,024 | 5,656 | copy |
| `ytk_videos` | 384 | 315 | copy |
| `ytk_videos_v2` | 1,024 | 200 | copy |
| `ytk_visual` | 1,152 | 422 | rebuild |
| `ytk_visual_pending` | 1,152 | 1,278 | rebuild |

The six text collections contain 20,497 healthy vectors. Both v1 and v2 text
collections remain available so the existing encoder rollback contract is
preserved.

## Considered Approaches

### 1. Fresh server, copy healthy vectors, rebuild visual vectors

Create a new server-owned data directory, copy all six healthy text
collections through Chroma's collection API, and regenerate the two visual
collections from source images.

This is the selected approach. It avoids copying damaged HNSW files, preserves
the exact text vectors and retrieval geometry, and leaves the old embedded
directory intact for rollback.

### 2. Serve the existing embedded directory

Stop all clients and run `chroma run --path ~/.ytk/chroma`, then delete and
rebuild the visual collections.

This is rejected because the new server would inherit the damaged segment and
all other storage artifacts from the incident. Deleting or counting the broken
collection may itself block.

### 3. Re-embed every collection into a fresh server

Regenerate text and visual embeddings from the vault.

This is rejected because it would combine a storage-topology migration with an
encoder replay, take substantially longer on a 16 GB M3 MacBook Pro, and risk
retrieval drift despite no intended search-quality change.

## Target Architecture

```text
Hub ───────────────┐
MCP servers ───────┤
CLI and schedules ─┼── HTTP on 127.0.0.1:8000 ──> Chroma server
Map/dedupe scripts ┘                                  │
                                                     └── ~/.ytk/chroma-server
```

Only the Chroma server opens SQLite and HNSW files. Every ytk process uses
`chromadb.HttpClient`.

The service binds to `127.0.0.1`, not `0.0.0.0`, and uses no cloud service or
external network. Authentication is unnecessary because the socket is
loopback-only.

Qwen3 and SigLIP remain inside ytk processes for this migration:

- Qwen3 continues to embed documents and queries with the existing
  instruction-aware prefix rules.
- SigLIP continues to produce 1,152-dimensional image and text vectors.
- Chroma receives the same vectors as before; only storage and nearest-neighbor
  execution move into the server process.

## Runtime Configuration

The runtime environment gains:

```dotenv
CHROMA_URL=http://127.0.0.1:8000
CHROMA_SERVER_PATH=~/.ytk/chroma-server
```

`CHROMA_PATH=~/.ytk/chroma` remains the explicit legacy source and rollback
path. Client selection is evaluated when the client is created, after the CLI
has loaded `~/.ytk/.env`.

When `CHROMA_URL` is set, production code creates `HttpClient`. When it is
absent, tests and explicit migration-source readers may use
`PersistentClient`. Tests must force isolated embedded mode and must never
inherit the production URL.

The hub settings endpoint reports the active Chroma mode, URL, server data
path, and embedding epoch without presenting the legacy path as the live
store.

## Service Lifecycle

ytk owns a `com.ytk.chroma` launchd agent with:

- `RunAtLoad=true`
- `KeepAlive=true`
- `chroma run --host 127.0.0.1 --port 8000`
- persistence at `~/.ytk/chroma-server`
- logs at `~/.ytk/logs/chroma.log`

The public CLI lifecycle is:

```bash
ytk chroma install
ytk chroma restart
ytk chroma status
ytk chroma uninstall
```

`ytk chroma serve` is the foreground command used by launchd. It replaces
itself with the `chroma` executable from the same installed environment so
signals and exit status reach the actual server.

The lifecycle code resolves executable and home-directory paths before writing
the plist. It does not require rebuilding `/Applications/ytk.app` or changing
its Full Disk Access identity.

The hub may start before Chroma after login. Hub startup therefore waits for a
bounded server heartbeat before initializing the application. A failed wait
exits with a clear error so launchd can retry instead of starting a partially
functional ingest service.

## Migration

The migration command copies collections through two separate clients:

- source: `PersistentClient(path=CHROMA_PATH)`
- target: `HttpClient(CHROMA_URL)`

It refuses to run unless:

- the target server responds to heartbeat;
- source and target resolve to different storage locations;
- no target collection contains data unless `--resume` is supplied;
- the visual circuit breaker remains off during text migration.

For each non-visual collection, it:

1. creates the target collection with the source collection's metadata;
2. reads IDs, documents, metadata, and embeddings in bounded batches;
3. upserts the batch into the target;
4. compares source and target counts;
5. records the verified count in a migration report.

The command never calls `count()`, `get()`, or `delete_collection()` on either
legacy visual collection. Visual collection names are excluded before a source
collection object is opened.

The report is written atomically under `~/.ytk/recovery/` and includes source
path, target URL, collection counts, excluded collections, start/end time, and
completion status.

`--resume` is idempotent: target upserts use the original IDs, and count
validation must still pass before completion.

## Visual Rebuild

After text cutover:

1. set `CHROMA_URL` for all new ytk processes;
2. enable `YTK_VISUAL_INDEX`;
3. create fresh `ytk_visual` and `ytk_visual_pending` collections on the server;
4. rebuild saved covers from vault notes and their image paths;
5. rebuild pending covers from the queue and `~/.ytk/covers`;
6. compare the saved index to discoverable vault covers and the pending index
   to cached covers for currently pending items;
7. run representative stored-ID, text-to-image, and pending-image similarity
   queries.

The rebuild does not read embeddings or HNSW files from either damaged legacy
visual collection.

The circuit breaker remains permanent defense-in-depth. Re-enabling visual
search means removing the runtime `off` state, not deleting the guard.

## Cutover Sequence

1. Verify the ingest queue is idle.
2. Back up `~/.ytk/.env`, both launchd plists, and runtime queue/job state.
3. Install code containing HTTP client and migration support.
4. Install and start `com.ytk.chroma` with the fresh server path.
5. Stop the hub and terminate any pre-migration MCP processes.
6. Copy and verify all six healthy text collections.
7. Set `CHROMA_URL` in `~/.ytk/.env`.
8. Start the hub and verify text search before rebuilding visual collections.
9. Enable and rebuild both visual collections.
10. Restart the hub and fresh MCP processes.
11. Run live readiness, ingest, text-search, write/read, and visual-search
    checks.

The write outage begins when the hub stops and ends after text search and a
temporary write/read check succeed against the server.

## Rollback

The original `~/.ytk/chroma` directory is never modified or deleted during
this migration.

If text migration or server validation fails:

1. stop `com.ytk.chroma`;
2. restore the backed-up environment and launchd files;
3. keep `YTK_VISUAL_INDEX=off`;
4. start only the hub against the legacy embedded directory;
5. keep MCP and concurrent CLI writers stopped until the server migration is
   retried.

The fresh `~/.ytk/chroma-server` directory is retained for diagnosis. It is not
overwritten or deleted automatically.

After successful cutover, the legacy directory remains a read-only recovery
artifact until a later explicitly approved cleanup.

## Failure Handling

- Client construction reports the configured URL when the server is
  unreachable; it never silently falls back to embedded mode.
- Service status distinguishes launchd loaded, TCP reachable, and Chroma
  heartbeat healthy.
- Migration count mismatches fail the run and preserve the report.
- Partial target collections require explicit `--resume`; normal runs never
  merge into unknown target state.
- Visual rebuild failure leaves text search operational and restores
  `YTK_VISUAL_INDEX=off`.
- The visual subprocess probe remains in place for corrupted or unresponsive
  server-side visual indexes.

## Testing

### Unit tests

- environment parsing selects embedded or HTTP mode correctly;
- invalid or non-loopback production URLs are rejected;
- production URL cannot leak into isolated tests;
- launchd plist generation contains the exact executable, host, port, path,
  logs, and restart policy;
- migration excludes both visual names before opening source collections;
- copying preserves IDs, documents, metadata, embeddings, collection metadata,
  and counts;
- resume is idempotent;
- settings diagnostics report the active server topology.

### Integration tests

- start a real Chroma server on an ephemeral loopback port and temporary path;
- connect through ytk's `HttpClient` factory;
- create, upsert, count, query, and delete a temporary collection;
- copy a real temporary embedded collection into the server;
- stop the server and verify the client does not fall back to embedded mode.

### Live verification

- all six text collection counts match the legacy store;
- retrieval evaluation gate passes without a baseline update;
- a temporary memory write is immediately searchable and removable;
- hub readiness, root, settings, and ingest-status endpoints respond;
- multiple concurrent client processes can read and write without opening
  `~/.ytk/chroma-server` files themselves;
- both rebuilt visual collections answer `count()` promptly;
- representative visual searches return non-empty results;
- full Python and web test suites pass.

## Model-Service Follow-Up

Qwen3 and SigLIP can later be moved behind a separate local embedding service.
That would share model memory across hub, MCP, and CLI processes and remove
per-process cold starts. Qwen3 is the stronger candidate because semantic
search is common and its MPS model is warmed by several process types.

This is not part of the Chroma migration. It changes vector-production
boundaries, document upserts, query-prefix handling, model lifecycle, and
failure behavior. After server cutover, measure process RSS, aggregate MPS
memory, cold-start frequency, and request latency. Create a separate design
only if those measurements justify the added service.

## Success Criteria

- No ytk production process uses `PersistentClient` against the live store.
- Only `com.ytk.chroma` opens the live SQLite and HNSW files.
- All six healthy text collections retain exact counts and retrieval behavior.
- Both visual collections are rebuilt without reading legacy visual data.
- `YTK_VISUAL_INDEX` is enabled and representative visual search works.
- Hub, MCP, CLI, scheduled jobs, map build, and dedupe script use the server.
- Chroma starts automatically at login and recovers under launchd.
- Rollback artifacts remain intact.
