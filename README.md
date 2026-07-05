# ytk

A personal knowledge system for the things you watch and read. ytk fetches
transcripts and metadata from YouTube videos (plus Instagram, TikTok,
Pinterest, and web articles), enriches them with Claude Haiku, writes atomic
notes into an Obsidian vault, and indexes embeddings locally in ChromaDB so
everything is semantically searchable — from the CLI, from a local web hub,
or from inside a Claude Code session via MCP.

## Philosophy

ytk is a complement to watching, not a replacement. The premise is that you
still watch the video — ytk exists so that three weeks later, when you think
"how did that guy drive the television from the CLI?", you can find the exact
moment. Enrichment is tuned for density of named specifics (tools, commands,
techniques, timestamps), not vague summaries.

The second premise: your own words carry the signal. Every capture path lets
you attach a note — a thought typed at queue time, a voice memo, an
annotation in the inbox — and those annotations are embedded and searched
alongside the source content. Over time the system synthesizes an interest
profile from what you actually save and say about it.

## Architecture

```
capture                 enrich                store                 retrieve
-------                 ------                -----                 --------
ytk add (YouTube)   ->  Claude Haiku      ->  Obsidian vault    ->  ytk search / dive
ytk ingest (web)        (thesis, summary,     (markdown notes,      hub pages (:6969)
ytk reels (IG DMs)      key concepts,         thumbnails,           MCP server
ytk add-tiktok          insights, tags,       frames)               interest profile
ytk memo (voice)        key moments)          ChromaDB
hub inbox queue                               (embeddings)
```

- Transcripts come from `youtube-transcript-api` first, with a `yt-dlp`
  subtitle fallback and a local faster-whisper fallback for audio-only cases.
- Notes are plain markdown with frontmatter — the vault stays a normal
  Obsidian vault, usable without ytk.
- Embeddings are computed locally with sentence-transformers; nothing leaves
  your machine except the enrichment call to the Anthropic API.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/pablomoli/ytk
cd ytk
uv sync
uv run ytk --help

# or install the CLI globally
uv tool install .
# after pulling changes: uv tool install --reinstall .
```

`ffmpeg` is needed for voice memos and frame extraction.

## Configuration

Copy `.env.example` to `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault
CHROMA_PATH=~/.ytk/chroma
INSTAGRAM_SESSIONID=        # only for ytk reels; see caveats
INSTAGRAM_PEER=             # optional two-account capture thread
```

Runtime settings live in `~/.ytk/config.yaml` (auto-created with defaults).
It holds ingest filters (min/max duration, caption requirement, optional
interest-tag gate), hub host/port, inbox annotation chips, fetch cadence per
source, and interest-model parameters. The hub's `/settings` page is a
validated editor over this file, with inline documentation of every field.

## Quickstart

```bash
ytk add https://www.youtube.com/watch?v=VIDEO_ID     # ingest one video
ytk add <url> --force                                # bypass filters
ytk add <url> --note "why I saved this"              # steer enrichment
ytk ingest <article-url>                             # web article
ytk feed urls.txt                                    # batch ingest

ytk search "query"                                   # semantic search, whole vault
ytk dive VIDEO_ID "query"                            # segment-level, timestamped
ytk memo                                             # record a voice memo, auto-route
ytk profile                                          # synthesize interest profile
ytk ui                                               # start the hub at :6969
```

Other commands: `add-instagram`, `add-tiktok`, `add-pinterest`, `reels`
(Instagram DM capture-thread sync), `triage` / `review` (action extraction
and GitHub routing), `graph` (HTML knowledge graph), `tags`, `remember`,
`reindex`, `gc`, `snap`, `chat`, `dashboard`, `visual index` / `visual
similar`. Run `ytk --help` for the full list.

## The hub

`ytk ui` serves a local web app:

- `/` — fresh feed of recent ingests
- `/inbox` — queue picker with buckets and annotation chips; a paste box adds
  anything to the queue; your thoughts are embedded into search and the daily
  digest
- `/tags` — tag gardening: merge enrichment-coined tag variants; accepted
  merges persist via an alias map
- `/map` — 3D brain map, a UMAP projection of every text embedding
- `/settings` — validated editor over `~/.ytk/config.yaml`

On macOS, `ytk ui install` registers the hub as a launchd daemon
(`ytk ui status` / `ytk ui restart` / `ytk ui uninstall`).

## MCP server for Claude Code

ytk ships an MCP server (`ytk-mcp` entry point) exposing the vault to Claude
sessions: `vault_read`, `vault_write`, `vault_search`, `vault_list`,
`vault_remember`, `vault_reindex`, `vault_update_index`, `visual_similar`.

```bash
# with the CLI installed globally (uv tool install .):
claude mcp add --scope user ytk -- ytk-mcp
# or straight from a checkout:
claude mcp add --scope user ytk -- uv run --directory /path/to/ytk ytk-mcp
```

This is the primary interface in practice — a Claude Code session can search
everything you have ever saved, and capture decisions back into the vault.

## What's personal, what's portable

This started as a single-user tool and some edges show:

- **Instagram (`ytk reels`, `add-instagram`)** needs a `sessionid` cookie
  from a logged-in browser session, and works best with a dedicated
  second account as the capture thread. Instagram may flag bot-shaped
  traffic; the hub throttles pulls per source for this reason.
- **macOS-flavored bits**: the launchd daemon (`ytk ui install`), the
  `ytk schedule` nightly launchd job (index + dashboard), voice-memo capture via ffmpeg with
  macOS notifications, and iMessage ingestion (`add-imessage`) all assume
  macOS. Core ingest/search works anywhere Python and ffmpeg do.
- **Vault layout**: the enrichment prompts and vault conventions (a
  `second-brain/` tree with wiki, memories, sources) reflect one person's
  system. The note format is plain markdown; adapt the paths and it is
  yours.
- **Costs**: enrichment uses `claude-haiku-4-5` per ingest; everything else
  (embeddings, transcription, search) runs locally.

## License

MIT — see [LICENSE](LICENSE).
