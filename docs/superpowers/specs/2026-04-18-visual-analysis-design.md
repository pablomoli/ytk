# Visual Analysis — Design Spec

**Date:** 2026-04-18
**Issue:** #1
**Status:** approved

---

## Summary

Add visual analysis to ytk so that both YouTube videos and Instagram posts are enriched with Claude's vision capabilities. Visual analysis is the core differentiator from tools like graphify. The existing `Enrichment` model and vault schema are unchanged.

---

## Goals

- YouTube: always extract baseline frames + targeted frames at moments flagged by hint detection
- Instagram: analyze carousel images and reel keyframes as the primary content source; caption is secondary context
- Single multimodal enrichment call per item (not two-pass describe-then-enrich)
- New `ytk add-instagram <url>` CLI command, end-to-end

---

## Non-Goals

- No new fields in `Enrichment` — visual descriptions flow into the same fields via the prompt
- No UI changes (Phase 6)
- No Instagram authentication / Stories / private accounts
- No real-time or streaming video analysis

---

## Architecture

### New files

**`ytk/vision.py`** — visual analysis primitives, three responsibilities:

1. `hint_detect(segments: list[dict]) -> list[float]`
   - Heuristic pass: scan segment text for visual cue phrases ("as you can see", "on screen", "in this diagram", "let me show", "the code here", "look at this", etc.)
   - If zero heuristic hits: return `[]` immediately (skip Haiku call entirely)
   - If one or more hits: call Claude Haiku with the full transcript asking it to return a JSON list of timestamps (seconds) where visual content is important — catches implicit moments like "let's try it" before a live demo
   - Returns deduplicated, sorted list of float timestamps

2. `extract_frames(video_path: Path, timestamps: list[float], baseline_n: int = 4) -> list[bytes]`
   - Merges hint timestamps with `baseline_n` evenly-spaced timestamps across video duration
   - Shells out to ffmpeg via `subprocess` (already used in `cli.py`) to extract one JPEG per timestamp
   - Returns list of raw JPEG bytes; temp files cleaned up after read
   - Skips gracefully if ffmpeg not found

3. `image_blocks(urls: list[str] | None = None, frame_bytes: list[bytes] | None = None) -> list[dict]`
   - Builds Anthropic API content blocks
   - For URLs: uses `{"type": "image", "source": {"type": "url", "url": "..."}}` (Instagram CDN URLs are valid at ingest time)
   - For bytes: base64-encodes and uses `{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}}`
   - Falls back to base64 for any URL that returns a non-2xx response on HEAD check

**`ytk/instagram.py`** — Instagram media fetcher, one responsibility:

- `fetch_instagram(url: str) -> InstagramPost` where `InstagramPost` is a dataclass with:
  - `images: list[str]` — CDN URLs for all carousel images (single post = list of one)
  - `video_url: str | None` — reel/video download URL if present
  - `caption: str` — post caption text (nice-to-have context)
  - `username: str`, `timestamp: str`, `url: str`
- Uses `instaloader` (public posts only, no auth required) for fetching
- For reels: downloads video to a temp path (via yt-dlp, consistent with existing audio download pattern), returns path as `video_url`

### Modified files

**`ytk/enrich.py`**

```python
def enrich(
    transcript: str,
    metadata: dict,
    visual_blocks: list[dict] | None = None,
) -> Enrichment:
```

- When `visual_blocks` is `None`: behavior identical to today (string content, system prompt cached)
- When `visual_blocks` is present: `user_content` becomes a list — metadata/transcript text block(s) interleaved with image blocks. Claude sees everything in one pass.
- System prompt gets one added sentence: "You may also receive images or video frames — incorporate what you observe in them into your analysis."
- The `cache_control` on the system prompt stays; this one-time change is cheap.

**`ytk/cli.py`**

New command `ytk add-instagram <url>`:

```
instagram_fetch(url)
→ image_blocks(image_urls)
→ [if video_url: extract_frames(video_path) → image_blocks(frame_bytes)]
→ enrich(caption, instagram_meta, visual_blocks)
→ write_vault (sources/instagram/)
→ upsert
```

Modified `ytk add` (YouTube):

```
fetch_metadata → fetch_transcript
→ hint_detect(segments)
→ extract_frames(video_path, hint_timestamps, baseline_n=4)
→ image_blocks(frame_bytes)
→ enrich(transcript, meta, visual_blocks)
→ write_vault → upsert
```

The YouTube video is downloaded to temp via yt-dlp only when frame extraction is needed (always, per decision). Temp file is cleaned up after frames are extracted.

---

## Data Flow

```
YouTube:
  url
  → fetch_metadata()             # yt-dlp metadata
  → fetch_transcript()           # segments [{start, duration, text}]
  → hint_detect(segments)        # heuristic → optional Haiku → [timestamps]
  → yt-dlp download video-only stream (temp mp4, no audio — lighter than full download)
  → extract_frames(mp4, timestamps, baseline_n=4)  # → [JPEG bytes]
  → image_blocks(frame_bytes)    # → Claude content blocks
  → enrich(transcript, meta, visual_blocks)
  → write_note() → upsert()

Instagram:
  url
  → fetch_instagram(url)         # instaloader → InstagramPost
  → image_blocks(image_urls)     # CDN URLs → content blocks
  → [reel: yt-dlp download → extract_frames → image_blocks appended]
  → enrich(caption, meta, visual_blocks)
  → write_instagram_note() → upsert()
```

---

## Vault Storage

Instagram notes go to `sources/instagram/<username>-<date>-<slug>.md`. Format mirrors the YouTube note format: frontmatter with `url`, `username`, `date`, `tags`, then Summary, Key Concepts, Insights, Key Moments (where moments = image index or reel timestamp).

`vault.py` gets a new `write_instagram_note(post: InstagramPost, result: Enrichment) -> Path` function alongside the existing `write_note()`. The existing function is not modified.

---

## Error Handling

- ffmpeg not found: log warning, skip frame extraction, enrich text-only
- Instagram fetch fails (private account, rate limit): surface clear error, exit 1
- Any image URL 4xx/5xx: skip that image, log, continue with remaining
- Haiku hint-detect call fails: fall back to heuristic timestamps only

---

## Dependencies

- `instaloader` — new addition to `pyproject.toml`
- `ffmpeg` — system dependency (already present via yt-dlp on most setups); document in README
- No other new deps; base64, subprocess, tempfile are stdlib

---

## Testing Approach

- `test_vision.py`: unit-test `hint_detect` with synthetic segments (assert heuristic hits, assert Haiku skipped when no hits)
- `test_vision.py`: unit-test `image_blocks` with mock URLs and byte inputs
- Integration: `ytk add-instagram <public post url>` smoke test in CI is optional — Instagram rate limits make this fragile; manual verification is acceptable for now
