# scripts/

Standalone utility scripts for ytk. Run with `uv run scripts/<name>.py`.

## seed_memory.py

Scrapes `~/.claude/projects/` session JSONLs across all Claude Code projects and generates long-term memory summaries using Claude Haiku. Writes each summary as an atomic note to `inbox/memories/` in the Obsidian vault and indexes it in ChromaDB.

Automatically invoked by the Claude Code Stop hook after every session (`--recent` mode). Can also be run manually to seed all projects at once.

```bash
uv run scripts/seed_memory.py                    # process projects with no existing memory file
uv run scripts/seed_memory.py --force            # regenerate all, overwriting existing
uv run scripts/seed_memory.py --dry-run          # preview extracted turns without calling Claude
uv run scripts/seed_memory.py --max-sessions 5   # read more sessions per project (default: 3)
uv run scripts/seed_memory.py --recent           # reseed only the most recently active project
uv run scripts/seed_memory.py --recent --dry-run # preview which project --recent would target
```

`--recent` skips silently if the most recent session JSONL is older than 5 minutes (avoids redundant runs on shell restarts).

## reindex.py

Re-processes all ingested videos through the current enrichment pipeline. Useful after prompt changes — fetches fresh transcripts and metadata, re-runs Claude Haiku enrichment, overwrites vault notes, and re-upserts ChromaDB embeddings.

```bash
uv run scripts/reindex.py             # reindex all processed videos
uv run scripts/reindex.py --dry-run   # show what would be reindexed
uv run scripts/reindex.py <video_id>  # reindex a single video by ID
```
