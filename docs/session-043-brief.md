# ytk — Session 043 Brief

**Date:** 2026-07-26
**Mode:** Chroma incident containment and hub recovery

## Outcome

The hub is responsive again with visual indexing temporarily disconnected.
Text search, capture, ingestion, and enrichment remain available. Visual
similarity, visual profile pools, and cover indexing now degrade to neutral
results without opening either Chroma visual collection.

The completed astronomy memo was already present in the vault as
`memo_2026-07-25-2110-i-should-make-the-next-ytk-visualization-027cd2`.
Its single stale pending entry and persisted ingest-job entry were removed
after timestamped backups. No note or Chroma data was deleted.

## Root Cause

`ytk_visual` has a damaged HNSW segment. Its `count()` blocks inside Chroma
1.5.9's Rust binding while holding the Python GIL, which freezes every thread
in the process, including uvicorn's event loop.

The astronomy memo itself did not call `ytk_visual`. It completed the vault and
text-index writes, then its process stopped returning during a text-memory
Chroma operation. The hub and multiple `ytk-mcp` processes were concurrently
using one embedded `PersistentClient` database. Embedded Chroma is safe across
threads but is not a supported concurrent multi-process writer topology.

The damaged visual collection explains the deterministic visual hang. The
shared embedded database topology explains why non-visual ingestion can still
become stuck under multiple ytk processes.

## Changes

- Added a dynamic `YTK_VISUAL_INDEX=off` circuit breaker in `ytk.store`.
- Routed every public visual read, write, delete, and metadata operation through
  the same subprocess-backed health gate.
- Added neutral disabled-mode results: zero counts, empty IDs and result pools,
  missing embeddings and metadata, false metadata updates, and no-op mutations.
- Stopped cover and pending-cover indexing before vault scanning or SigLIP model
  startup when visual indexing is unavailable.
- Replaced `/api/visual-image`'s private collection access with the guarded
  `get_visual_metadata()` store API.
- Isolated pytest from the production runtime flag and live visual probe.

Relevant commits:

- `c3d402b` — storage-boundary circuit breaker
- `ec40750` — visual orchestration and endpoint containment
- `879432d` — test isolation for the runtime switch

Design and execution documents:

- `docs/superpowers/specs/2026-07-26-visual-index-circuit-breaker-design.md`
- `docs/superpowers/plans/2026-07-26-visual-index-circuit-breaker.md`

## Runtime Recovery

`YTK_VISUAL_INDEX=off` is set in `~/.ytk/.env`.

Backups:

- `~/.ytk/recovery/ingest-job.json.20260726T060459Z.bak`
- `~/.ytk/recovery/reels_state.json.20260726T060459Z.bak`

The pending queue changed from 3,604 to 3,603 items and the persisted job list
from one to zero. The astronomy iMessage session remains in `imessage_seen`.

`launchctl kickstart -k` restarted the app wrapper, but the frozen Python child
survived as an orphan owned by PID 1 and kept port 6969 open. PID 35412 was
identified by `lsof` as the old listener and terminated. The newly installed
hub then bound the port normally.

## Verification

```text
Focused visual/store/hub tests     69 passed
Full Python suite                  816 passed, 1 deselected
Live /api/ready                    responsive
Live /api/ingest/status            running=false, queued=[]
Live hub root                      HTTP 200
Live port owner                    new installed hub process
Repository commits                 pushed to origin/master
```

## Permanent Follow-Up

Issue #130 remains open. The durable repair is:

1. Move all ytk processes from embedded `PersistentClient` access to one local
   Chroma server.
2. Route the hub, MCP servers, and CLI through that single service.
3. Rebuild `ytk_visual` and `ytk_visual_pending` from vault covers and pending
   cover cache.
4. Validate counts and representative similarity queries.
5. Remove `YTK_VISUAL_INDEX=off` and verify the circuit breaker passes its
   health probe.

Do not re-enable the visual index against the current damaged collection.
