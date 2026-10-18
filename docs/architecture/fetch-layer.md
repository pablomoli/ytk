# The fetch layer

Layer one of ingestion: a URL's content in seconds, before and apart from
the curator. No model calls, no ledger rows, no asks. Layer two (the curator
engine, `docs/architecture/curator-engine.md`) can adopt what layer one
fetched, but layer one never waits on it.

## What runs

`ytk/fetch.py`. `fetch(url)` returns a `Fetched`: a plain `EvidenceBundle`
plus `meta` (timings, storyboard grid, kept video, background work). One
directory per URL under `evidence/fetch/<key>/`:

| file | what |
|---|---|
| `bundle.json` | the `EvidenceBundle`; the curator's read step adopts it |
| `meta.json` | timings per step, storyboard grid, kept video path, Whisper state |
| `content.md` | the chat rendering (head, chapters, description or caption, body, transcript) |
| `sheet.jpg` | the contact sheet |
| `storyboard/NNN.jpg` | YouTube's storyboard grids, kept for span sheets |
| `video.*`, `dense/`, `shown/` | reels and TikToks: the whole video and its frame tier |
| `closeups/`, `span-*.jpg` | what `fetch_frames` made |

One writer per entry: `fetch` holds an `flock` on `<key>/.lock`, so a
second fetch of the same URL waits and then reads. Files are written to a
temp name and renamed, `meta.json` last; an entry without a readable
`meta.json` is fetched again. The detached Whisper run takes the same lock
to write back, and only if the entry still names its own pid: a refetch
in between owns the entry, and a refetch while Whisper runs keeps that run
instead of starting a second.

The key is the canonical URL: `youtube:<id>` for every YouTube shape
(watch, `youtu.be`, `/shorts/`, `/live/`, `&t=`), the path without query
for Instagram and TikTok (share links carry `igsh=` and `_r=`), the URL
without fragment for the web. A second fetch of any shape is a disk read
(0.36 s through the CLI, process start included).

Surfaces:

- MCP `fetch_url(url, refresh=False)`: the rendering (capped at 60k
  characters; the cut names `content.md`) plus the sheet as an image.
- MCP `fetch_frames(url, at=[s...])`: up to six full-resolution frames.
  `fetch_frames(url, start=, end=)`: a denser sheet of that stretch.
- `ytk add <url>`: fetches and prints the head and the `content.md` path,
  then captures into the ledger as before. `--no-keep` skips the capture;
  `--print` writes the whole rendering to stdout and status to stderr. A
  failed fetch is reported and never blocks the capture.
- `evidence.read_item` adopts a cached bundle (activity `inputs`
  `{"from": "fetch-cache"}`) when a video's transcript is finished;
  otherwise the gatherer runs as before. `retry_parked` never adopts.

## Per source

**YouTube.** One yt-dlp `extract_info` (no cookies: Zen cookies make
YouTube extraction fail with "Requested format is not available"). From
that one info dict, side by side:

- captions: the `srv1` URL of the best track. The video's own language
  first, manual before auto; `<lang>-orig` is recognition of the real
  audio. Machine translations and recognition of dubbed audio are never
  picked.
- storyboard: the `sb0` grids (3x3 tiles of ~320x180 per JPEG), all
  downloaded in parallel. The tile interval is the fragment duration over
  nine; 48 evenly spaced tiles make the sheet.

When no caption can be read, Whisper (base, int8, CPU) runs in a detached
process (`python -m ytk.fetch <dir>`, own session) over the audio track and
writes back into the same entry; the fetch returns at once saying "pending,
about N s". A run that dies is reported as a gap on the next fetch, not
waited on.

**Instagram and TikTok.** yt-dlp downloads the whole video (best mp4; Zen
cookies for Instagram, never an instagrapi login; nothing for TikTok). The
#202 frame tier and contact sheet run over it, Whisper runs in-process up
to 180 s of media and detached past that. The video is kept, so close-ups
are local ffmpeg reads at native resolution. The caption is the bundle's
`caption` for Instagram and `description` for TikTok, as the gatherers file
them. If yt-dlp fails on an Instagram post (image carousels), the error
surfaces; the curator gatherer remains the path for those.

**Web.** trafilatura with formatting, tables and images kept: code fences
survive, relative image links are resolved against the page. arXiv `/abs/`
is rewritten to the paper (arXiv HTML from 2312 on, ar5iv before) and the
gap says so.

**Reddit, Pinterest.** The existing gatherers, unchanged.

## Measured (2026-10-18, M3, sequential runs)

| step | time | notes |
|---|---|---|
| YouTube metadata | 1.2-2.3 s | 0 bot checks in 13 plain extractions |
| captions (srv1) | 0.4-0.7 s | when not rate-limited |
| storyboard sheet | 0.35-0.9 s, any length | sb0 tile every 1 s (56 s video) to 10 s (cap, 1950 s and up) |
| whole YouTube fetch, warm | 2.8-5 s | 2 h 20 min video included |
| close-up, 2 s section at <=1080p | 4-6 s each, 4 in parallel in 6 s | 4/4 including t=6000 s of a 2 h video |
| reel/TikTok download | 0.7-3.2 s | 0.6-7 MB |
| reel frame tier and sheet | 0.14-0.75 s | |
| Whisper base int8 | 3-7 s per reel; 31.7-53 s per 6.5-10.5 min video | about 0.1 s per second of media |
| web | 0.3-2.4 s | GitHub README 128k characters, clean |
| cache hit | 0.36 s through the CLI | |

Legibility, checked by eye on the images:

- storyboard tiles (320x180): titles, equations, slide text and burned-in
  captions read; editor-sized code does not, only its layout.
- a 1080p close-up of the same moment: every line of code reads.
- reel sheet tiles: captions, QR examples, diagrams read; small tables are
  borderline.

## What is not possible, or not yet

- **Captions under a rate limit.** After the bench made dozens of caption
  requests, YouTube answered 429 on every caption route for this IP: the
  timedtext URL directly, yt-dlp's subtitle download, with and without
  browser cookies. Storyboards and video were unaffected. The fetch falls
  back to Whisper, so a blocked 10 min video costs about 50 s of background
  transcription instead of 0.5 s. How long such a block lasts is unknown.
- **Remote seeks for close-ups.** ffmpeg `-ss` against the stream URL
  succeeded 3-4 times of 7 (63 s on one, 403 on long videos). Section
  downloads through yt-dlp replaced it.
- **A no-caption YouTube video** was never found: all 60 ledger videos and a
  3.2 h music video carried auto captions. The Whisper path is exercised by
  rate limits, not by missing tracks.
- **Diagrams on the web.** trafilatura keeps `<img>` links but not inline
  SVG: the Pingora post has 11 `<img>` and 68 `<svg>`, 3 image links
  survive. Images are links, not fetched pixels.
- **Instagram image carousels** are not handled by the yt-dlp path.
- **Whisper quality.** Base int8 mishears names ("election apps" for
  Electron). Larger models or an MLX build would be slower or a new
  dependency; unmeasured.
