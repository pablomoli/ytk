# Phase 5: Second Brain — MCP + Vault Automation

**Date:** 2026-04-16
**Status:** Approved, awaiting implementation
**Approach:** Option A — thin MCP wrapper over existing ytk modules

---

## Overview

ytk currently creates memories via one path: `ytk add <url>`. This phase makes the vault a true second brain by exposing it to Claude Code sessions via an MCP server, enabling Claude to search, read, and write arbitrary notes — not just YouTube video notes. Nightly automation keeps the vault index and a daily dashboard current without manual intervention.

---

## Architecture

The MCP server (`ytk/mcp_server.py`) imports directly from the existing `vault.py`, `store.py`, and `db.py` modules. No new abstraction layer is introduced. The CLI and MCP are parallel consumers of the same module-level functions.

```
ytk/
  mcp_server.py      — MCP server, imports vault.py + store.py + db.py
  vault.py           — existing: note read/write (extended for generic notes)
  store.py           — existing: ChromaDB upsert + search
  db.py              — existing: SQLite tracking
  cli.py             — extended: ytk index, ytk dashboard, ytk schedule
pyproject.toml       — new script entry point: ytk-mcp
```

Claude Code connects to the server via `settings.json` under `mcpServers`. The server is launched as `uv run ytk-mcp`.

---

## MCP Tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `vault_search` | `(query: str, n: int = 5)` | Semantic search via ChromaDB across all vault content |
| `vault_read` | `(path: str)` | Read any vault note by relative path from vault root |
| `vault_list` | `()` | Return current `wiki/index.md` contents |
| `vault_write` | `(path: str, content: str)` | Write or overwrite a note at any vault path |
| `vault_remember` | `(text: str, tags: list[str] = [])` | Create an atomic memory note and index it |
| `vault_update_index` | `()` | Regenerate `wiki/index.md` by scanning vault |

### `vault_remember` detail

The key new primitive. Stores arbitrary text (a decision, insight, brainstorming summary, guide) as an atomic note at:

```
inbox/memories/YYYY-MM-DD-{slug}.md
```

Frontmatter:
```yaml
---
date: YYYY-MM-DD
tags: [<tags>]
type: memory
---
```

After writing, upserts the note to ChromaDB so it is semantically searchable alongside video notes. This is how Claude stores memories that don't originate from YouTube.

---

## New CLI Commands

### `ytk index`

Scans the entire vault and rebuilds `wiki/index.md` from scratch. Replaces the current implicit update-on-add behavior that produces duplicate entries.

Sections generated: `wiki/`, `projects/` (grouped by project, sorted by date), `inbox/`, `sources/youtube/` (deduplicated by video ID), `decisions/`, `debugging/`, `tools/`.

Called by `vault_update_index` MCP tool and by the nightly scheduler.

### `ytk dashboard`

Generates `inbox/review-YYYY-MM-DD.md` as a static snapshot of vault state. Content:

- **Recent memories** — notes in `inbox/memories/` from the last 7 days
- **Recent videos** — videos added since the last dashboard
- **Active projects** — entries in `projects/` with a link to each project's latest session brief
- **Inbox items** — files in `inbox/` that are not dated review files

Overwrites any existing file for today's date. Does not call Claude — pure file system read.

> **Future phase:** add a `--ai` flag that pipes the snapshot to Claude Haiku for a synthesized digest ("here's what you've been learning about lately").

### `ytk schedule install` / `ytk schedule uninstall`

Installs or removes a launchd plist at `~/Library/LaunchAgents/com.ytk.nightly.plist`. The job runs `ytk index && ytk dashboard` each morning at 6am (configurable). Logs to `~/.ytk/nightly.log`.

---

## Claude Code Registration

`~/.claude/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "ytk": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ytk", "ytk-mcp"]
    }
  }
}
```

`pyproject.toml` gets a new script entry point:

```toml
[project.scripts]
ytk = "ytk.cli:cli"
ytk-mcp = "ytk.mcp_server:main"
```

---

## Out of Scope

- AI-synthesized dashboard (flagged for future phase)
- MCP write access to personal vault folders (`JOURNAL/`, `Daily/`, `LEETCODE/`)
- Multi-user or remote vault access
- Phase 6 (local UI), Phase 7 (iMessage pipeline)
