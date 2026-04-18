# ytk — Session 001 Brief

**Date:** 2026-04-13
**Phase:** 2 — Filters

## What Was Built

Phase 2 of the ytk ingestion pipeline: a config-driven filter layer that gates
ingestion before and after the expensive transcript + enrichment steps.

### New files

- `ytk/config.py` — Pydantic config model (`Config`, `FilterConfig`) loaded
  from `~/.ytk/config.yaml`. Missing file returns safe defaults. Config path
  overridable via `YTK_CONFIG` env var.

- `ytk/filter.py` — Two filter checkpoints:
  - `check_pre_transcript(meta, cfg)` — structural checks on metadata alone
    (min_duration, max_duration). Runs before transcript fetch.
  - `check_post_enrichment(enrichment, cfg)` — semantic check on Haiku output
    (interest_tags). Runs after full enrichment. Tag matching is
    case-insensitive and normalises hyphens/underscores/spaces.
  - Returns `FilterResult(passed, failures)` — importable by the future
    scheduler without any CLI coupling.

### Modified files

- `ytk/cli.py` — `add` command now:
  1. Loads config via `load_config()`
  2. Runs `check_pre_transcript` after metadata fetch; prompts user on failure
  3. Catches transcript fetch errors; if `require_captions=True`, prompts user
  4. Runs `check_post_enrichment` after enrichment; prompts user on failure
  5. Accepts `--force` flag to skip all prompts (always continues)

- `pyproject.toml` — added `pyyaml>=6.0`

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Two-checkpoint design | Fail fast on duration (free) before paying for transcript + Haiku |
| Prompt, not hard-reject | User preference — manual adds should be interactive, not opaque |
| `filter.py` returns `FilterResult`, knows nothing about Click | Scheduler (Phase 3) will call same functions in silent/skip mode |
| Tag normalisation (hyphen/underscore/space) | Tags grow fast; users write them inconsistently |
| `interest_tags: []` = allow all | Sensible default — don't filter until you've configured tags |
| Captions check during fetch, not pre-check | Availability can only be confirmed by attempting fetch; avoids a separate yt-dlp probe call |

## Config Format

Default location: `~/.ytk/config.yaml`

```yaml
filters:
  min_duration: 60        # seconds (default: 1 min)
  max_duration: null      # no upper limit
  require_captions: true
  interest_tags:          # empty = allow all
    - go
    - geospatial
    - creative-coding
    - ai
```

## Commands to Run

```bash
# Install / sync dependencies
uv sync

# Run on a video (interactive filter prompts)
uv run ytk add https://www.youtube.com/watch?v=VIDEO_ID

# Bypass all filters
uv run ytk add https://www.youtube.com/watch?v=VIDEO_ID --force

# After uv tool install .
ytk add <url>
ytk add <url> --force
```

## What's Next

- **Phase 3 — Vault (Obsidian):** `vault.py` writing atomic notes in
  claude-obsidian format. Set `OBSIDIAN_VAULT_PATH` in `.env` first.
- **Phase 3 — Scheduler:** YouTube Data API v3 OAuth, poll "ytk" playlist
  nightly, filter.py reused in silent mode (auto-skip instead of prompt).
- **Phase 3.5 — Claude Code vault hooks:** session end → write brief to vault.
  This brief should ultimately land at `projects/ytk/session-001-brief.md`
  inside the Obsidian vault once the vault path is configured.
