# ytk — Architecture & Roadmap

## Session start (do this first)

The ytk MCP server is registered globally. At the start of every session:

1. Call `vault_read("second-brain/wiki/hot.md")` — latest project state and commands
2. Call `vault_read("second-brain/wiki/index.md")` — full vault index
3. Drill into `second-brain/projects/ytk/` as needed via `vault_read`
4. Call `vault_read("second-brain/inbox/memories/index.md")` — project memory MOC. Drill into `second-brain/inbox/memories/{project}/` atoms as needed.

Use `vault_search("query")` to retrieve any past decision, session brief, or memory.

Then read `docs/llm-operating-guide.md` — the vault contract: what goes where, which MCP tool for which job, when NOT to write a note, and session rituals. It overrides habit.

---

## Git hygiene (non-negotiable)

Never leave anything uncommitted in this repo. Before ending a session, the working tree must be clean (`git status` shows nothing). Commit all changes in coherent logical commits with descriptive messages, then push.

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
| 5I | done | Visual/image saving — YouTube thumbnails + frames, Instagram images, Obsidian embeds |
| 5J | done | Atomic memory LYT — folder-based atom notes per project with differential Haiku updates |
| 5K | done | Triage + review commands — action extraction, GitHub routing, interactive/auto modes |
| 6 | done | Local vault UI — `ytk ui` (FastAPI + SSE chat at :8765) + `ytk chat` (Claude in ytk context) |
| 7 | done | iMessage + TikTok capture pipeline → ytk/GitHub/Obsidian routing |
| 8 | done | Interest model — `ytk feed` batch ingest + `ytk profile` (embedding clustering → XML profile at `me/profile.md`) |
| 8.5 | partial | Audiobook tracker — stdlib epub fuzzy text-position matcher (`books_match.py`); CLI not yet wired |
| 9 | done | `ytk reels` — Instagram DM capture-thread sync (instagrapi discovery → pending queue → interactive picker → existing `add` pipeline) |
| 10 | done | Ingest hub — `ytk ui` reborn: / fresh feed, /inbox queue picker with buckets + thoughts (annotations embed into search + daily digest), paste-to-queue Add box; chat at /chat |
| 11 | done | `ytk memo` — voice memo capture: ffmpeg record, faster-whisper STT, Claude routing, focus-aware notify, hub POST /api/memo |
| 12 | done | Brain map — `scripts/build_map.py` (UMAP of all text embeddings, fitted params, theme-painted) + hub `/map` canvas page |

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
    vault.py           — Obsidian note writer and MCP vault tools
    store.py           — ChromaDB upsert + search
    interest.py        — interest-model data types + snapshot persistence
    synthesis.py       — embedding clustering → XML interest profile (me/profile.md)
    graph.py           — HTML knowledge-graph builder
    vision.py          — frame extraction + Claude vision image blocks
    triage.py          — action-item extraction for `ytk triage`
    books_match.py     — stdlib epub fuzzy text-position matcher (audiobook tracker)
    reels.py           — Instagram DM link discovery + source-agnostic pending queue (`ytk reels`)
    memo.py            — voice memo pipeline: record, transcribe, route, notify (`ytk memo`)
    ui/hub.py          — ingest-hub backend: queue ops, background ingest job, fresh feed
    ui/static/         — hub pages: fresh.html (/), inbox.html (/inbox), index.html (/chat)
  docs/architecture/
    cli-decomposition.md          — witness-first extraction map for `ytk/cli.py`
    map-renderer-decomposition.md — resource ownership and extraction map for the WebGL renderer
```

The interest profile at `second-brain/me/profile.md` is rendered as XML (frontmatter
+ `<interest-profile>` with ranked, weighted `<theme>` nodes and `<exemplar>` titles)
so an agent can traverse it structurally. Re-render from the latest snapshot without
an API call via `ytk profile --render-only`.

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

## Just command reference

Run `just --list` from anywhere inside the repository to see the supported
development and operational commands.

```bash
just setup         # install Python development and frontend dependencies
just check         # run the complete repository quality gate
just lint          # lint all supported Python and frontend source
just typecheck     # run Pyright and TypeScript checks
just test          # run the fast Python and Chromium frontend suites
just build-web     # rebuild the local web bundle (dev serving only)
just ui            # run the hub in the foreground
just install-tool  # reinstall the ytk CLI from this checkout
```

The pre-commit hook is intentionally incremental; `just check` is the complete
gate. Python quality commands require the `dev` extra. Frontend tests run in
real Chromium with `vp exec vitest run`; the Vite+ beta's integrated test path
does not load this project's test binary correctly.

`web/dist` is gitignored (#108): the wheel builds its own bundle via
`hatch_build.py` (`vp build` at build time, loud failure if the bundle is
missing or trivial), so `uv tool install --reinstall .` needs no prior manual
build or dist commit. `just build-web` only refreshes the local bundle that
`ytk ui` serves in dev. `just eval` uses the live Chroma
store and frozen retrieval corpus; never update its baseline merely to clear a
failure. Installed CLI changes require `uv tool install --reinstall .`.

Chroma is a separately managed local server. Run `just chroma-status` before
debugging storage behavior. Start foreground servers and other long-running
recipes in a visible tmux pane after listing panes; do not hide them in an
unobserved background process.

## CSS policy (#136)

Hand-written CSS only shrinks. `web/css-budget.json` pins a per-file line
ceiling enforced by `tests/test_css_budget.py`; `scripts/ratchet_css.py` locks
gains in and refuses to raise a ceiling. New chrome styles itself with Tailwind
utilities against the observatory tokens (`web/src/theme.css`, aliased in
`web/src/tw.css`); interactive primitives are vendored Radix/shadcn components
in `web/src/components/ui/`. What remains in `styles.css` and the route CSS is
deliberately bespoke — identity surfaces and not-yet-touched chrome — never add
rules there. `theme.css` is the identity layer and is exempt from the ratchet.
Page controls render inside their page, never in the nav bar.

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
- `key_moments` — timestamped moments specific enough to find from memory. **No cap**: the
  prompt says "include as many as the content warrants; scale to length", and notes in the
  corpus carry up to 40. Whether a cap would help is untested — see
  `docs/assets/09-heatmap-key-moments/notes.md`

## arXiv ingestion convention (verified 2026-07-27)

Never ingest an arXiv `/abs/` page. It succeeds and yields a near-useless note —
abstract plus arXivLabs boilerplate, no paper — and the failure is silent, so
search, `/quiz`, and concept notes all run against an abstract believing they
hold the source. Rewrite first:

| arXiv id | Ingest |
|---|---|
| `2312.*` and newer | `https://arxiv.org/html/<id>v1` |
| older | `https://ar5iv.labs.arxiv.org/html/<id>` |

Then **patch the frontmatter**: ar5iv extraction reliably yields an empty
`author:` and a `date:` scraped from the references (measured 3/3 wrong, each
differently — the 2020 Kaplan paper came out as 2015-11-01). Correct values come
from the keyless arXiv API:

```bash
curl -sL "http://export.arxiv.org/api/query?id_list=<id>"   # <published>, <name>
```

Set `author:` (first author + ` et al.`), `date:`, and `arxiv:` as part of
ingestion, not as later cleanup — a plausible-but-wrong date corrupts every
date-sorted view silently. `transformer-circuits.pub`, `distill.pub`, and
`gwern.net` need no rewrite and extract cleanly.

Note that `sources/web/` notes carry no raw body (unlike `sources/youtube/`,
which keeps `## Transcript`), so grounding a claim in the source means
re-fetching `url:`. Tracked as part of #92; metadata gaps as part of #144.

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

## Retrieval eval gate (#85)

Never change search behavior without running the gate. `uv run ytk eval` scores
the frozen known-item query set (`eval/retrieval/queries.jsonl`, 156 queries)
against the live store through the production search paths and fails on
regression vs `eval/retrieval/baseline.json` (stamped with epoch + date).
Scoring is restricted to the document ids in `eval/retrieval/frozen_corpus.json`,
captured when the baseline was stamped (#111). The vault grows every day, so a
gate that measured the whole live store went red on ingest rather than on
quality and taught everyone to `--no-verify` past it. Documents added since the
stamp are still retrieved — the searchers over-fetch, then filter — but are not
scored, so growth cannot move hit@k while a genuine ranking regression still
shows. If too many queries have their window eaten by newer documents the gate
says so explicitly rather than quietly understating retrieval.
`--update-baseline` re-stamps the baseline and the freeze together after an
intentional change; never re-stamp to clear a red gate, which launders the
regression into the new baseline. A pre-commit hook
(`scripts/git-hooks/pre-commit`, installed via `git config core.hooksPath
scripts/git-hooks`) runs it automatically when `ytk/store.py`,
`ytk/retrieval_gate.py`, or `eval/retrieval/` change. Live end-to-end test:
`uv run pytest -m eval`.

## Obsidian Vault

Path: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault`
Configured in `.env` as `OBSIDIAN_VAULT_PATH`.

**At session start:** read `second-brain/wiki/hot.md` first, then `second-brain/wiki/index.md`, then drill into `second-brain/projects/ytk/` as needed. Also read `second-brain/inbox/memories/index.md` and drill into the relevant project atoms.

**At session end (non-negotiable):** write a session brief to `second-brain/projects/ytk/session-NNN-brief.md`. Include what was built, decisions and rationale, what's next, and exact commands to run the project. Mirror a copy to `docs/session-NNN-brief.md` in the repo.

**At planning session end:** write a planning brief instead (goals, options considered, decision made, open questions).

**When writing new vault files:** update `second-brain/wiki/index.md` to keep it current.

### Vault layout (claude-obsidian layer)
```
second-brain/wiki/hot.md              — hot cache, read first each session
second-brain/wiki/index.md            — lightweight index of all vault content
second-brain/projects/ytk/            — session briefs, specs, decisions
second-brain/inbox/ideas.md           — loose ideas and backlog items
second-brain/inbox/review-[date].md   — daily routing digest (phase 7)
second-brain/me/profile.md            — living interest profile (ytk profile, interest-model synthesis)
second-brain/inbox/memories/index.md  — project memory MOC (all projects)
second-brain/inbox/memories/{slug}/   — per-project atom folder
  index.md                            — project hub (wikilinks to atoms)
  purpose.md                          — what this project is and why it exists
  tech.md                             — stack, tools, key architectural decisions
  state.md                            — current status, blockers, recent changes
  questions.md                        — open questions and unknowns
  recent.md                           — most recent session summary (always overwritten)
second-brain/sources/youtube/         — ingested video notes from ytk pipeline
  thumbnails/                         — {video_id}-thumb.jpg for every ingested video
  frames/{video_id}/                  — extracted frames (ytk add only, when visual cues found)
second-brain/sources/instagram/       — ingested Instagram notes; slides/{shortcode}-img-N.*, thumbnails/, frames/
second-brain/decisions/               — architectural decision records
second-brain/debugging/               — bug patterns and resolutions
second-brain/tools/                   — notes on libraries and tools
```

<claude-mem-context>
# Recent Activity

<!-- This section is auto-generated by claude-mem. Edit content outside the tags. -->

*No recent activity*
</claude-mem-context>
