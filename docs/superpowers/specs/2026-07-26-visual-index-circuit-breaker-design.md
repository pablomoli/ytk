# Visual index circuit breaker

## Problem

The persisted `ytk_visual` Chroma collection is damaged: a raw `count()` never
returns. Chroma's Rust binding holds Python's interpreter lock while blocked,
which freezes the hub instead of raising an exception. The existing health
probe protects similarity queries, but direct reads and writes can still reach
the damaged collection through post-ingest cover indexing, screenshot ingest,
profile evaluation, note deletion, image serving, CLI commands, and the MCP
visual-search tool.

Visual embeddings are derived data. Their authoritative inputs are the saved
images and vault notes, so disabling the collection does not affect enrichment,
vault writes, memo routing, text search, or transcript search.

## Decision

Add a storage-boundary circuit breaker controlled by
`YTK_VISUAL_INDEX=off`. When disabled, no production function may create,
read, update, query, or delete either visual collection.

The storage API will return neutral values:

- counts return `0`;
- ID readers return empty sets;
- embedding readers return `None`;
- similarity and profile-pool readers return empty lists;
- metadata updates return `False`;
- writes and deletes become no-ops.

The higher-level visual indexing functions will check the same switch before
loading SigLIP, scanning covers, or attempting Chroma access. This avoids
wasting memory and compute while the subsystem is intentionally offline.

The default remains enabled so existing behavior is unchanged unless the
operator explicitly sets the environment variable. The hub LaunchAgent will
set the switch to `off` for the temporary containment period.

## Recovery

After deployment:

1. Confirm the astronomy memo already exists in the vault and text index.
2. Remove its completed URL from the pending queue and clear the persisted
   ingest-job entry so restart does not duplicate it.
3. Restart the hub.
4. Verify `/api/ready`, `/api/ingest/status`, and the SPA respond.
5. Run an ingestion-path test with visual indexing disabled and confirm no
   visual collection accessor is called.

## Follow-up boundary

This circuit breaker contains the damaged visual collection but does not make
embedded Chroma process-safe. The permanent follow-up is a single local Chroma
server with all hub, MCP, CLI, and scheduled-job access going through HTTP.
Repairing and rebuilding `ytk_visual` belongs to that migration, not this
containment change.
