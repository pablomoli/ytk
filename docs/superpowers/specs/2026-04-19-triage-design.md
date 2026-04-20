# ytk triage — Design Spec

**Date:** 2026-04-19
**Status:** Approved

## Overview

`ytk triage` extracts structured action items from any vault note using Claude Haiku and routes them interactively to GitHub issues, `inbox/ideas.md`, or `inbox/review.md`. A companion `ytk review` command surfaces pending investigate items.

## Architecture

Three new pieces added to the existing ytk structure:

1. **`ytk/triage.py`** — extraction module
2. **Config extension** — `github_repos` list in `~/.ytk/config.yaml`
3. **Two CLI commands** — `ytk triage` and `ytk review`

## Components

### `ytk/triage.py`

- `ActionItem` (Pydantic): `title: str`, `description: str`, `priority: Literal["high", "medium", "low"]`, `suggested_route: Literal["gh-issue", "idea", "investigate"]`
- `TriageResult` (Pydantic): `items: list[ActionItem]`
- `extract_action_items(note_text: str) -> list[ActionItem]` — Claude Haiku structured output call. Only extracts concrete actionable items; skips vague aspirations. Returns empty list if none found.

System prompt emphasis: imperative titles (<70 chars), 1-2 sentence descriptions with enough context to act without re-reading, priority based on urgency signals in the note, route suggestion based on item type (software task → gh-issue, loose idea → idea, needs research → investigate).

### Config extension (`config.py`)

```yaml
github_repos:
  - melocoton/ytk
  - melocoton/epic-map
```

Added as `github_repos: list[str] = []` to the Pydantic config model. Shown as a numbered pick-list when the user routes an item to GH.

### `ytk triage [NOTE_PATH]`

**Flow:**
1. Resolve note path — if omitted, find most recently modified `.md` in `$OBSIDIAN_VAULT_PATH/sources/` by mtime (pipeline notes land here, not under `second-brain/`)
2. Read note text
3. Run `extract_action_items` (Claude Haiku)
4. Display all items in a single panel showing title, description, priority, and suggested route
5. Route each item interactively:
   - **[1] GH issue** — show numbered list of `github_repos` from config, prompt to pick; run `gh issue create --title ... --body ... --repo owner/name`; print issue URL on success
   - **[2] Inbox/ideas** — prompt optional due date (YYYY-MM-DD or blank); append checkbox entry to `$OBSIDIAN_VAULT_PATH/second-brain/inbox/ideas.md`
   - **[3] Review** — append checkbox entry to `$OBSIDIAN_VAULT_PATH/second-brain/inbox/review.md` with source note name and date
   - **[4] Skip** — move on
6. Print summary of what was routed where

**Default route:** suggested by Claude, shown to user but not auto-applied.

### `ytk review`

Reads `$OBSIDIAN_VAULT_PATH/second-brain/inbox/review.md` and prints all unchecked items (`- [ ]`) in a Rich table with columns: item title, source note, date added. Checked items (`- [x]`) are filtered out. If file doesn't exist or is empty, prints a friendly message.

### `inbox/review.md` format

```markdown
- [ ] Item title — *source-note-filename* (2026-04-19)
  Description of what to investigate.
```

Checkbox format for Obsidian Tasks plugin compatibility. `second-brain/inbox/ideas.md` uses the same format with optional `(due: YYYY-MM-DD)`.

### Config creation

`~/.ytk/config.yaml` does not exist by default. `load_config()` already handles a missing file by returning defaults. Adding `github_repos` to the `Config` model is sufficient — no file creation needed. Users populate the list manually or via a future `ytk config` command.

## Error Handling

- `gh` not installed or repo not found: print error, re-prompt the user to pick a different route for that item — don't abort the whole triage session
- Vault not configured: exit early with clear message before extraction runs
- No action items found: print message and exit cleanly
- Note path not found: exit with clear message

## Testing

Manual test with today's journal note (`sources/journal/Apr-19-...md`). Verify:
- All three routes work end-to-end (GH issue created, ideas.md appended, review.md appended)
- `ytk review` correctly filters checked vs unchecked items
- Default-to-latest-note resolution works without a path argument
- `gh` failure re-routes correctly without crashing

## What's Out of Scope

- Bulk-routing all items to the same destination
- Editing action item text before routing
- Auto-closing review items from the CLI
- Scheduling or reminders beyond a due date string
