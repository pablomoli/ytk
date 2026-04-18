# Shared Brain Sprint — Design Spec

**Date:** 2026-04-16
**Status:** Approved, awaiting implementation plan
**Scope:** Five targeted gaps identified in Phase 5 architecture review

---

## Overview

Phase 5 shipped the MCP read/write path, but the shared brain only works if both sides actively write to it. This sprint closes five gaps: user-side CLI capture, vault writes that are invisible to search, no global session-end capture rule, YouTube-only ingestion, and memories that accumulate forever without lifecycle management.

---

## Phase 5B — `ytk remember` CLI

**What:** User-side quick capture from the terminal.

**Interface:**
```bash
ytk remember "text" [--tags foo,bar]
echo "text" | ytk remember --tags foo,bar   # stdin
```

**Behavior:** Calls `vault.remember()` + `store.upsert_memory()`. Prints the note path. Tags are comma-separated; empty tags list is valid.

**Location:** New `@cli.command()` in `ytk/cli.py`. No new modules needed.

---

## Phase 5C — Auto-index vault writes

**What:** Every write to the vault is indexed in ChromaDB so `vault_search` finds it.

**Two changes:**

1. `vault_write` MCP tool: after writing to disk, strip YAML frontmatter and upsert the body text to `ytk_memories` collection using the relative path as doc ID.

2. New `vault_reindex` MCP tool + `ytk reindex` CLI command: scans `inbox/memories/`, `projects/`, `decisions/`, `debugging/`, `tools/` and bulk-upserts all `.md` files. Skips `sources/youtube/` (already indexed separately in `ytk_videos`/`ytk_segments`). Idempotent — safe to re-run.

**Store changes needed:** `upsert_doc(doc_id, text, metadata_dict)` as the shared primitive; `upsert_memory` becomes a thin wrapper over it. `seed_memory.py` and `mcp_server.py` callers of `upsert_memory` need no changes — signature is unchanged. Add `delete_doc(doc_id)` for Phase 5F.

**Frontmatter stripping:** Before upserting vault note content, strip the YAML frontmatter block (everything between `---` delimiters at the top) so ChromaDB indexes the body text only, not the metadata fields.

---

## Phase 5D — Global session-end capture

**What:** One sentence in `~/.claude/CLAUDE.md` that makes every Claude session contribute to the vault.

**The rule:**
> At the end of any session where significant decisions, architectural choices, or non-obvious learnings occurred, call `vault_remember` with a concise summary. Include the project name as a tag. The ytk MCP (`vault_remember`) is registered globally and available in all projects.

**No code changes.** The MCP is already globally registered. This is purely a behavioral instruction.

---

## Phase 5E — `ytk ingest <url>` for web content

**What:** Fetch any URL, extract readable text, enrich with Haiku, store in vault + ChromaDB.

**New module:** `ytk/ingest.py`

```python
@dataclass
class WebContent:
    url: str
    title: str
    author: str
    date: str
    text: str

def fetch_web(url: str) -> WebContent   # trafilatura extraction
def enrich_web(content: WebContent, client) -> Enrichment   # Haiku, reuses Enrichment model
```

**`enrich_web` prompt:** Same `Enrichment` schema as YouTube. Adjusted system prompt — swap "transcript" for "article" and drop key_moments (articles have no timestamps). `key_moments` returns empty list.

**Vault note:** Written to `sources/web/{slug}.md`. Same frontmatter shape as YouTube notes minus `duration`. `_slug()` from `vault.py` reused for filename.

**CLI:**
```bash
ytk ingest https://example.com/article
ytk ingest <url> --force   # skip filters
```

**Filter behavior:** Runs `check_post_enrichment` for interest tag filtering (same as `ytk add`). No pre-transcript filter (no duration to check).

**New dependency:** `trafilatura>=1.6`

---

## Phase 5F — `ytk gc` memory lifecycle

**What:** Surface stale memories and archive them out of ChromaDB.

**Interface:**
```bash
ytk gc                     # list memories with age, no changes
ytk gc --prune 60          # archive memories older than 60 days
ytk gc --refresh-projects  # re-run seed for project memories older than 30 days
ytk gc --dry-run           # show what --prune would do
```

**Prune behavior:** Moves `.md` files to `inbox/memories/archived/`. Removes from ChromaDB via `store.delete_doc(doc_id)`. Doc IDs are stored in the note frontmatter (`id:` field added by `vault.remember()`).

**Refresh-projects behavior:** Reads `inbox/memories/*.md` tagged `project-context`, checks mtime, re-runs `scripts/seed_memory.py --force` for projects whose memory is older than 30 days. Requires `ANTHROPIC_API_KEY`.

**`vault.remember()` change:** Add `id:` field to frontmatter so gc can retrieve the ChromaDB doc ID without re-deriving it.

---

## Phase 5G — Stop hook: automatic post-session reseed

**What:** A Claude Code Stop hook that re-seeds the current project's vault memory immediately after every session ends. No manual intervention, no judgment required.

**Hook registration:** Added to `~/.claude/settings.json` under `hooks.Stop`:

```json
{
  "type": "command",
  "command": "cd /path/to/ytk && uv run scripts/seed_memory.py --recent --max-sessions 1 >> ~/.ytk/seed.log 2>&1"
}
```

Runs in the background after Claude stops. Output logged to `~/.ytk/seed.log`.

**`--recent` flag on `seed_memory.py`:** Finds the project directory whose `.jsonl` file was most recently modified (i.e., the session that just ended), re-seeds only that project. Skips all others. Exactly one Haiku call per session end.

**Behavior:**
- Session ends in epicmap → Stop hook fires → `--recent` finds epicmap's latest JSONL → Haiku re-summarizes → vault memory updated
- If no JSONL modified in the last 5 minutes, no-op (avoids redundant calls on shell restarts or non-session stops)
- `--force` is implied for the targeted project so the existing memory gets overwritten with fresh context

**`seed_memory.py` change:** Add `--recent` flag. When set, scan all project dirs, find the one with `max(mtime)` across all `.jsonl` files, run seeding for that project only with `--force`.

---

## Out of scope

- Haiku-powered staleness detection (can't detect without current project context)
- Automatic de-duplication of similar memories
- ChromaDB indexing of `sources/youtube/` (already handled by `store.upsert`)
- Any UI changes

---

## Implementation order

1. Store primitives (`upsert_doc`, `delete_doc`) — everything else depends on these
2. 5D (CLAUDE.md rule) — zero-risk, instant payoff
3. 5B (`ytk remember`) — closes user write path
4. 5C (`vault_write` fix + `vault_reindex`) — closes search gap
5. 5E (`ytk ingest`) — new module, largest surface
6. 5F (`ytk gc`) — depends on `id:` frontmatter from updated `vault.remember()`
7. 5G (Stop hook + `--recent` flag) — wires automation, depends on seed script being stable
