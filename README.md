# ytk

Personal YouTube knowledge system. Ingests videos into an Obsidian vault with AI enrichment and semantic search.

## How it works

```
ytk add <url>
  -> fetch metadata (yt-dlp)
  -> fetch transcript (youtube-transcript-api, yt-dlp fallback)
  -> filter (duration, captions, interest tags)
  -> enrich (Claude Haiku: thesis, summary, key concepts, insights, key moments)
  -> write Obsidian note (sources/youtube/<title>.md)
  -> index embeddings (ChromaDB, all-MiniLM-L6-v2)

ytk sync
  -> poll YouTube "ytk" playlist via Data API v3
  -> run full pipeline on each new video (silent, no prompts)

ytk search "query"
  -> cosine similarity over video-level embeddings

ytk dive <video_id> "query"
  -> cosine similarity over 60s segment embeddings within a specific video
```

## Install

```bash
uv sync
uv tool install .
```

Or run without installing:

```bash
uv run ytk <command>
```

## Configuration

### `.env` (project root or home directory)

```
ANTHROPIC_API_KEY=sk-ant-...
OBSIDIAN_VAULT_PATH=/path/to/your/vault
CHROMA_PATH=~/.ytk/chroma        # optional, default shown
```

### `~/.ytk/config.yaml` (auto-created with defaults on first run)

```yaml
filters:
  min_duration: 60        # seconds — skip videos shorter than this
  max_duration: null      # no upper limit
  require_captions: true  # skip videos with no captions
  interest_tags: []       # if non-empty, skip videos whose tags don't match
                          # e.g. [go, geospatial, creative-coding, ai]
```

## Commands

### `ytk add <url>`

Fetch, enrich, and ingest a single YouTube video.

```bash
ytk add https://www.youtube.com/watch?v=dQw4w9WgXcQ
ytk add <url> --force    # skip all filter prompts
```

Displays metadata, transcript preview, AI enrichment panels, then writes the vault note and indexes embeddings.

### `ytk sync`

Poll the YouTube playlist named "ytk" and ingest any new videos. Runs the full pipeline silently (no interactive prompts — filter failures are skipped, not prompted).

```bash
ytk sync
ytk sync --dry-run    # show what would be processed without running the pipeline
```

Requires OAuth setup (`ytk auth`) and a playlist named "ytk" in your YouTube account.

### `ytk auth`

One-time OAuth flow for the YouTube Data API v3.

```bash
ytk auth
```

Prints an auth URL, opens it in your browser, then asks you to paste the redirect URL from the address bar after authorizing. Saves a token to `~/.ytk/token.json`.

Requires `~/.ytk/client_secrets.json` — download from Google Cloud Console (YouTube Data API v3, OAuth 2.0 client ID, Desktop app type).

### `ytk search "query"`

Semantic search across all ingested videos.

```bash
ytk search "how do you implement a ring buffer in go"
ytk search "television TUI framework" -n 10
```

Results are ranked by cosine similarity and show thesis, commentary, match %, tags, and URL.

Options:
- `-n N` — number of results (default: 5)

### `ytk dive <video_id> "query"`

Segment-level semantic search within a specific video. Returns timestamped 60-second blocks ranked by relevance, with direct YouTube timestamp links.

```bash
ytk dive dQw4w9WgXcQ "how did he set up the model update loop"
ytk dive dQw4w9WgXcQ "error handling" -n 10
```

The `video_id` is the 11-character ID from the YouTube URL (the `v=` parameter).

Options:
- `-n N` — number of results (default: 5)

## Scripts

See [`scripts/README.md`](scripts/README.md).

## Storage layout

```
~/.ytk/
  config.yaml       — filter configuration
  ytk.db            — SQLite ingestion log (video_id, title, status, timestamps)
  token.json        — YouTube OAuth token
  client_secrets.json — Google OAuth client credentials
  chroma/           — ChromaDB persistent vector store
    ytk_videos/     — one document per video (thesis + summary + insights + concepts)
    ytk_segments/   — one document per 60s transcript block
```

## Vault layout

Notes are written to `$OBSIDIAN_VAULT_PATH/sources/youtube/<title>.md`.

```markdown
---
url: https://www.youtube.com/watch?v=...
title: ...
uploader: ...
date: YYYY-MM-DD
tags:
  - go
  - creative-coding
duration: 00:45:12
---

## Thesis
One sentence: what the video actually argues or demonstrates.

## Commentary
3-5 sentences with named specifics — tools, commands, techniques.

## Key Concepts
- concept name: how it was used in this specific video

## Insights
- non-obvious technique or gotcha worth remembering

## Key Moments
- **12:34** — specific description of what happens at this timestamp

## Transcript
<details>
<summary>Raw transcript</summary>
[0:00](https://youtu.be/...?t=0) ...
</details>
```

## See also

- [`CLAUDE.md`](CLAUDE.md) — architecture, phase roadmap, vault conventions
- [`scripts/README.md`](scripts/README.md) — utility scripts
