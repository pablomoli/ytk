# ytk — Session 005 Brief

**Date:** 2026-04-16
**Phase:** 5B-5G — Shared Brain Sprint

## What Was Built

### store.py — Generic indexing primitives
- `strip_frontmatter(text)` — regex-based YAML frontmatter stripper (robust to `---` in values)
- `upsert_doc(doc_id, text, metadata)` — generic upsert into `ytk_memories`; truncates at 8000 chars
- `delete_doc(doc_id)` — remove from ChromaDB by ID with debug logging
- `upsert_memory` refactored as thin wrapper over `upsert_doc`

### vault.py — Web notes + bulk reindex
- `remember()` now writes `id: {doc_id}` to frontmatter (enables `ytk gc` lifecycle)
- `write_web_note(url, title, author, date, enrichment)` — writes to `sources/web/{slug}.md`
- `reindex_vault() -> int` — scans inbox/memories, inbox, projects, decisions, debugging, tools; uses frontmatter `id:` when present to avoid duplicate ChromaDB entries

### ytk/ingest.py — Web content ingestion (new module)
- `WebContent` dataclass: url, title, author, date, text
- `fetch_web(url)` — trafilatura fetch + extract
- `enrich_web(content)` — Haiku enrichment via `messages.parse(output_format=Enrichment)`; `key_moments` forced to `[]`; 20k char text limit, 2048 max_tokens; module-level cached client

### mcp_server.py — MCP tool fixes
- `vault_write` now strips frontmatter and upserts body to ChromaDB after writing to disk
- `vault_reindex` tool added — delegates to `vault.reindex_vault()`

### cli.py — Four new commands
- `ytk remember "text" --tags foo,bar` — vault + ChromaDB quick capture; reads stdin if no arg
- `ytk reindex` — bulk-index vault notes
- `ytk ingest <url> [--force]` — web article fetch → Haiku → vault note + ChromaDB
- `ytk gc [--prune N] [--refresh-projects] [--dry-run]` — memory lifecycle management

### scripts/seed_memory.py — Stop hook support
- `--recent` flag: finds most recently modified JSONL across all projects, reseeds only that project with `--force`, skips if > 5 minutes old

### ~/.claude/settings.json — Stop hook
- Fires `seed_memory.py --recent --max-sessions 1` after every Claude session
- Output logged to `~/.ytk/seed.log`

### ~/.claude/CLAUDE.md — Global capture rule
- Instructs Claude to call `vault_remember` at session end for significant decisions/learnings

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| `reindex_vault` reads frontmatter `id:` | Two code paths (remember + reindex) must agree on ChromaDB ID or they create duplicate entries |
| `key_moments = []` enforced in code, not just prompt | Model may ignore prompt instruction; post-parse assignment is the guarantee |
| doc_id for web notes sanitized via `[^a-zA-Z0-9_-]` | ChromaDB ID restrictions; article titles often contain `+`, `:`, `()` |
| `--recent` has 5-min recency gate | Prevents redundant calls on shell restarts and non-session stops |
| Stop hook appends to `~/.ytk/seed.log` | Background process — needs durable log to diagnose failures without blocking |

## New Dependencies
- `trafilatura>=1.6` — web content extraction

## Commands
```bash
ytk remember "note" --tags foo,bar
echo "note" | ytk remember --tags foo
ytk reindex
ytk ingest https://example.com/article [--force]
ytk gc
ytk gc --prune 60 --dry-run
ytk gc --refresh-projects
```

## What's Next
- **Phase 6** — Local UI (TanStack Start): transcript viewer, vault browser
- **Phase 7** — iMessage capture pipeline → ytk/GitHub/Obsidian routing
