# ytk — Architecture & Roadmap

## Session start (do this first)

The ytk MCP server is registered globally. At the start of every session:

1. Call `vault_read("wiki/hot.md")` — latest project state and commands
2. Call `vault_read("wiki/index.md")` — full vault index
3. Drill into `projects/ytk/` as needed via `vault_read`

Use `vault_search("query")` to retrieve any past decision, session brief, or memory.

---

## Overview

`ytk` is a personal YouTube knowledge system. It fetches transcripts and metadata from YouTube videos, enriches them with AI, stores them as atomic notes in an Obsidian vault, and indexes embeddings locally for semantic search.

## Phase Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | done | CLI: fetch transcript + metadata + Claude Haiku enrichment |
| 2 | done | Filters: duration, captions, interest tags — config-driven via YAML |
| 3 | done | Obsidian vault writer + YouTube playlist scheduler + OAuth |
| 3.5 | done | Session scraper — seed long-term memory from `~/.claude` JSONLs |
| 4 | done | ChromaDB vector storage + `ytk search` |
| 4B | done | `ytk dive` — segment-level search with timestamp links |
| 5 | done | MCP server — expose vault + vector store to Claude sessions |
| 5B | done | `ytk remember` CLI — user-side quick capture |
| 5C | done | Auto-index vault writes — `vault_write` + `vault_reindex` MCP tools |
| 5D | done | Global session-end capture rule in `~/.claude/CLAUDE.md` |
| 5E | done | `ytk ingest <url>` — web article ingestion via trafilatura |
| 5F | done | `ytk gc` — memory lifecycle: prune + refresh-projects |
| 5G | done | Stop hook — auto-reseed active project after every session |
| 5H | done | graphify integration — Whisper fallback, SHA256 incremental cache, HTML knowledge graph |
| 6 | planned | Local UI (TanStack Start) — transcript viewer, vault browser |
| 7 | planned | iMessage capture pipeline → ytk/GitHub/Obsidian routing |

## Project Structure

```
ytk/
  pyproject.toml       — uv-managed dependencies
  .env                 — local config (gitignored)
  .env.example         — template
  CLAUDE.md            — this file
  docs/                — local session briefs (mirror of vault/projects/ytk/)
  ytk/
    cli.py             — click CLI entry point
    config.py          — Pydantic config model, loads ~/.ytk/config.yaml
    filter.py          — pre/post-enrichment filter checks
    metadata.py        — yt-dlp Python API wrapper
    transcript.py      — youtube-transcript-api + yt-dlp fallback
    enrich.py          — Claude Haiku enrichment
    vault.py           — Obsidian note writer (phase 3, not yet built)
    store.py           — ChromaDB upsert + search (phase 4, not yet built)
```

## Configuration (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault
CHROMA_PATH=~/.ytk/chroma
```

## Usage

```bash
# Install
uv sync
uv run ytk add <url>

# Bypass all filters
uv run ytk add <url> --force

# Or after `uv tool install --reinstall .`  (use --reinstall, not --force, to pick up code changes)
ytk add https://www.youtube.com/watch?v=...
ytk add <url> --force
```

## Filter Config

Default location: `~/.ytk/config.yaml` (auto-created with defaults if missing)

```yaml
filters:
  min_duration: 60        # seconds
  max_duration: null      # no upper limit
  require_captions: true
  interest_tags:          # empty = allow all
    - go
    - geospatial
    - creative-coding
    - ai
```

## Transcript Fetch Strategy

1. `youtube-transcript-api` — hits YouTube's timedtext API directly. Fast, no download. Works only when captions exist (manual or auto-generated).
2. `yt-dlp` fallback — downloads `.vtt` subtitle file and parses it. Slower but covers more videos.

## AI Enrichment Prompt

Sent to `claude-haiku-4-5` with full transcript + metadata. ytk is a **complement** to watching, not a replacement — the user watches many videos and wants to be able to look up specific details later ("how did that guy use the television CLI?"). Enrichment should be dense with named specifics: tools, commands, techniques, approaches.

Returns a structured `Enrichment` object:

- `thesis` — one precise sentence naming the specific thing built/argued/demonstrated
- `summary` — 3–5 sentences for someone who watched it and wants a sharp reminder; names tools/commands concretely
- `key_concepts` — tools, commands, APIs, techniques with one-sentence explanations of how each was used in this specific video (max 8)
- `insights` — 2–3 specific things worth remembering: gotchas, non-obvious tradeoffs, surprising techniques
- `interest_tags` — lowercase hyphenated topic labels
- `key_moments` — up to 8 timestamped moments specific enough to find from memory

## Obsidian Note Format (Phase 3)

```markdown
---
url: <video_url>
title: <title>
date: <upload_date>
tags: [<interest_tags>]
duration: <HH:MM:SS>
---

## Summary
<summary>

## Key Concepts
- <concept>

## Fun Facts
- <fact>

## Key Moments
- **0:00** — <description>

## Transcript
<details>
<summary>Raw transcript</summary>
<transcript>
</details>
```

## How to Add a New Video

```bash
ytk add https://www.youtube.com/watch?v=VIDEO_ID
```

## How to Search the Vault (Phase 4)

```bash
ytk search "query"
```

## Obsidian Vault

Path: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault`
Configured in `.env` as `OBSIDIAN_VAULT_PATH`.

**At session start:** read `wiki/hot.md` first, then `wiki/index.md`, then drill into `projects/ytk/` as needed.

**At session end (non-negotiable):** write a session brief to `projects/ytk/session-NNN-brief.md`. Include what was built, decisions and rationale, what's next, and exact commands to run the project. Mirror a copy to `docs/session-NNN-brief.md` in the repo.

**At planning session end:** write a planning brief instead (goals, options considered, decision made, open questions).

**When writing new vault files:** update `wiki/index.md` to keep it current.

### Vault layout (claude-obsidian layer)
```
wiki/hot.md              — hot cache, read first each session
wiki/index.md            — lightweight index of all vault content
projects/ytk/            — session briefs, specs, decisions
inbox/ideas.md           — loose ideas and backlog items
inbox/review-[date].md   — daily routing digest (phase 7)
sources/youtube/         — ingested video notes from ytk pipeline
decisions/               — architectural decision records
debugging/               — bug patterns and resolutions
tools/                   — notes on libraries and tools
```

<claude-mem-context>
# Recent Activity

<!-- This section is auto-generated by claude-mem. Edit content outside the tags. -->

*No recent activity*
</claude-mem-context>