# Instagram Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ytk add-instagram <url>` to fetch, visually analyze, and vault any public Instagram post — images, carousels, and reels — using Claude Haiku in a single multimodal enrichment call.

**Architecture:** Two new modules (`vision.py`, `instagram.py`) plus targeted edits to `enrich.py` (add `visual_blocks` param), `vault.py` (add `write_instagram_note`), and `cli.py` (new command). YouTube's `add` command is also extended to extract frames and pass them as visual context. All visual content flows into the existing `Enrichment` model — no schema changes.

**Tech Stack:** instaloader (Instagram scraping), ffmpeg/ffprobe (frame extraction), yt-dlp (reel + YouTube video download), anthropic SDK multimodal content blocks, Claude Haiku

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | Add `instaloader` dependency |
| `ytk/vision.py` | Create | `hint_detect`, `extract_frames`, `image_blocks`, `download_video_temp` |
| `ytk/instagram.py` | Create | `InstagramPost` dataclass, `fetch_instagram`, `_extract_shortcode`, `_download_reel` |
| `ytk/enrich.py` | Modify | Add `visual_blocks: list[dict] \| None = None` to `enrich()` |
| `ytk/vault.py` | Modify | Add `write_instagram_note(post, enrichment) -> Path` after `write_web_note` |
| `ytk/cli.py` | Modify | Add `add-instagram` command; extend `add` with frame extraction |
| `tests/test_vision.py` | Create | Unit tests for `hint_detect` and `image_blocks` |
| `tests/test_instagram.py` | Create | Unit tests for shortcode parsing and `fetch_instagram` |
| `tests/test_enrich_visual.py` | Create | Unit tests for `enrich()` with `visual_blocks` |
| `tests/test_vault_instagram.py` | Create | Unit tests for `write_instagram_note` |

---

### Task 1: Add instaloader dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add instaloader to the dependencies list**

In `pyproject.toml`, append `"instaloader>=4.10"` to the `dependencies` list:

```toml
dependencies = [
    "click>=8.1",
    "yt-dlp>=2024.1.1",
    "youtube-transcript-api>=0.6.2",
    "python-dotenv>=1.0",
    "rich>=13.0",
    "anthropic>=0.40.0",
    "pyyaml>=6.0",
    "google-api-python-client>=2.100",
    "google-auth-oauthlib>=1.0",
    "chromadb>=0.5",
    "sentence-transformers>=3.0",
    "mcp>=1.0",
    "trafilatura>=1.6",
    "faster-whisper>=1.0",
    "networkx>=3.0",
    "instaloader>=4.10",
]
```

- [ ] **Step 2: Sync and verify**

```bash
uv sync
uv run python -c "import instaloader; print(instaloader.__version__)"
```

Expected: prints a version string like `4.14.1` with no errors.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add instaloader"
```

---

### Task 2: Create `ytk/vision.py`

**Files:**
- Create: `ytk/vision.py`
- Create: `tests/test_vision.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_vision.py`:

```python
import base64
from unittest.mock import MagicMock, patch


def test_hint_detect_no_cues_skips_haiku():
    from ytk.vision import hint_detect

    segments = [{"start": 0.0, "text": "Hello everyone welcome to this podcast episode today."}]
    with patch("ytk.vision.anthropic.Anthropic") as mock_cls:
        result = hint_detect(segments)
    mock_cls.assert_not_called()
    assert result == []


def test_hint_detect_with_cues_calls_haiku():
    from ytk.vision import hint_detect

    segments = [
        {"start": 5.0, "text": "As you can see on screen this is the main dashboard."},
        {"start": 10.0, "text": "Let me show you what happens when we click here."},
    ]
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text="[5.0, 10.0]")]
    with patch("ytk.vision.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_resp
        result = hint_detect(segments)
    assert result == [5.0, 10.0]


def test_hint_detect_deduplicates_and_sorts():
    from ytk.vision import hint_detect

    segments = [{"start": 3.0, "text": "As you can see the code here is straightforward."}]
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text="[10.0, 3.0, 10.0]")]
    with patch("ytk.vision.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_resp
        result = hint_detect(segments)
    assert result == [3.0, 10.0]


def test_hint_detect_haiku_bad_json_returns_empty():
    from ytk.vision import hint_detect

    segments = [{"start": 0.0, "text": "look at this amazing result on screen"}]
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text="Sorry, I cannot help with that.")]
    with patch("ytk.vision.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_resp
        result = hint_detect(segments)
    assert result == []


def test_image_blocks_bytes():
    from ytk.vision import image_blocks

    raw = b"\xff\xd8\xff\xe0"  # JPEG magic bytes
    blocks = image_blocks(frame_bytes=[raw])
    assert len(blocks) == 1
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["type"] == "base64"
    assert blocks[0]["source"]["media_type"] == "image/jpeg"
    assert blocks[0]["source"]["data"] == base64.standard_b64encode(raw).decode()


def test_image_blocks_url_reachable():
    from ytk.vision import image_blocks

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 200
    with patch("ytk.vision.urllib.request.urlopen", return_value=mock_resp):
        blocks = image_blocks(urls=["https://cdn.example.com/img.jpg"])
    assert len(blocks) == 1
    assert blocks[0]["source"]["type"] == "url"
    assert blocks[0]["source"]["url"] == "https://cdn.example.com/img.jpg"


def test_image_blocks_url_unreachable_falls_back_to_base64():
    from ytk.vision import image_blocks

    raw = b"\xff\xd8\xff"
    call_count = 0

    def fake_urlopen(req_or_url, timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("connection refused")
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = raw
        return mock_resp

    with patch("ytk.vision.urllib.request.urlopen", side_effect=fake_urlopen):
        blocks = image_blocks(urls=["https://cdn.example.com/private.jpg"])
    assert len(blocks) == 1
    assert blocks[0]["source"]["type"] == "base64"


def test_image_blocks_empty_returns_empty():
    from ytk.vision import image_blocks

    assert image_blocks() == []
    assert image_blocks(urls=[], frame_bytes=[]) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_vision.py -v
```

Expected: `ModuleNotFoundError: No module named 'ytk.vision'`

- [ ] **Step 3: Create `ytk/vision.py`**

```python
"""Visual analysis primitives: hint detection, frame extraction, image blocks."""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import anthropic

_VISUAL_CUE_PHRASES = [
    "as you can see", "on screen", "in this diagram", "let me show",
    "the code here", "look at this", "over here", "in the image",
    "on the left", "on the right", "shown here", "displayed here",
    "in this chart", "in this graph", "in the terminal", "in the output",
]


def hint_detect(segments: list[dict]) -> list[float]:
    """Return timestamps (seconds) where visual content matters.

    Heuristic scan first — if no cue phrases match, the Haiku call is skipped entirely.
    When phrases are found, Haiku also catches implicit visual moments (live demos, etc.).
    """
    full_text = " ".join(s.get("text", "") for s in segments).lower()
    if not any(phrase in full_text for phrase in _VISUAL_CUE_PHRASES):
        return []

    transcript_with_ts = "\n".join(
        f"[{s['start']:.1f}s] {s.get('text', '')}" for s in segments
    )
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                "Return a JSON array of timestamps (seconds, as floats) where visual content "
                "is important in this transcript. Include on-screen references, code demos, "
                "tool demonstrations, and 'let me show you' moments. "
                "Return ONLY a JSON array like [12.5, 45.0]. No other text.\n\n"
                f"Transcript:\n{transcript_with_ts}"
            ),
        }],
    )
    try:
        timestamps = json.loads(response.content[0].text)
        if not isinstance(timestamps, list):
            return []
        return sorted({float(t) for t in timestamps if isinstance(t, (int, float))})
    except (json.JSONDecodeError, ValueError, IndexError):
        return []


def extract_frames(
    video_path: Path,
    timestamps: list[float],
    baseline_n: int = 4,
) -> list[bytes]:
    """Extract JPEG frames at hint timestamps plus evenly-spaced baseline frames.

    Returns raw JPEG bytes. Returns [] silently if ffmpeg/ffprobe is not installed.
    """
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(video_path),
            ],
            capture_output=True, text=True, check=True,
        )
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except (subprocess.CalledProcessError, KeyError, ValueError, FileNotFoundError):
        return []

    baseline = [duration * i / (baseline_n + 1) for i in range(1, baseline_n + 1)]
    all_ts = sorted({*timestamps, *baseline})

    frames: list[bytes] = []
    for ts in all_ts:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            subprocess.run(
                [
                    "ffmpeg", "-v", "quiet", "-ss", str(ts),
                    "-i", str(video_path), "-frames:v", "1",
                    "-f", "image2", str(tmp_path), "-y",
                ],
                capture_output=True, check=True,
            )
            frames.append(tmp_path.read_bytes())
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        finally:
            tmp_path.unlink(missing_ok=True)

    return frames


def image_blocks(
    urls: list[str] | None = None,
    frame_bytes: list[bytes] | None = None,
) -> list[dict]:
    """Build Anthropic API content blocks from CDN image URLs or raw JPEG bytes.

    For URLs: tries a URL-type block first (CDN URLs are valid at ingest time).
    Falls back to downloading and base64-encoding if the HEAD check fails.
    Silently skips images that cannot be loaded.
    """
    blocks: list[dict] = []

    for url in (urls or []):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status < 300:
                    blocks.append({"type": "image", "source": {"type": "url", "url": url}})
                    continue
        except Exception:
            pass
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = base64.standard_b64encode(resp.read()).decode()
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
            })
        except Exception:
            pass

    for raw in (frame_bytes or []):
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(raw).decode(),
            },
        })

    return blocks


def download_video_temp(url: str) -> Path:
    """Download a video-only stream to a temp .mp4 file via yt-dlp. Caller must unlink."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    subprocess.run(
        [
            "yt-dlp", "-f", "bestvideo[ext=mp4]/best[ext=mp4]/best",
            "--no-audio", "-o", str(tmp_path), "--no-playlist", url,
        ],
        capture_output=True,
        check=True,
    )
    return tmp_path
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
uv run pytest tests/test_vision.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add ytk/vision.py tests/test_vision.py
git commit -m "feat(vision): add hint_detect, extract_frames, image_blocks, download_video_temp"
```

---

### Task 3: Create `ytk/instagram.py`

**Files:**
- Create: `ytk/instagram.py`
- Create: `tests/test_instagram.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_instagram.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


def test_extract_shortcode_post():
    from ytk.instagram import _extract_shortcode
    assert _extract_shortcode("https://www.instagram.com/p/ABC123xyz/") == "ABC123xyz"


def test_extract_shortcode_reel():
    from ytk.instagram import _extract_shortcode
    assert _extract_shortcode("https://www.instagram.com/reel/DEF456abc/") == "DEF456abc"


def test_extract_shortcode_tv():
    from ytk.instagram import _extract_shortcode
    assert _extract_shortcode("https://www.instagram.com/tv/GHI789/") == "GHI789"


def test_extract_shortcode_invalid_raises():
    from ytk.instagram import _extract_shortcode
    with pytest.raises(ValueError, match="Cannot extract shortcode"):
        _extract_shortcode("https://www.instagram.com/explore/tags/art/")


def test_fetch_instagram_single_image():
    from ytk.instagram import fetch_instagram, InstagramPost

    mock_post = MagicMock()
    mock_post.typename = "GraphImage"
    mock_post.url = "https://cdn.instagram.com/image.jpg"
    mock_post.is_video = False
    mock_post.owner_username = "testuser"
    mock_post.date_utc.strftime.return_value = "2026-04-19"
    mock_post.caption = "A beautiful shot #photography"

    with patch("ytk.instagram.instaloader") as mock_il:
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.return_value = mock_post
        result = fetch_instagram("https://www.instagram.com/p/ABC123/")

    assert isinstance(result, InstagramPost)
    assert result.username == "testuser"
    assert result.timestamp == "2026-04-19"
    assert result.images == ["https://cdn.instagram.com/image.jpg"]
    assert result.video_path is None
    assert result.caption == "A beautiful shot #photography"


def test_fetch_instagram_carousel():
    from ytk.instagram import fetch_instagram

    node1, node2 = MagicMock(), MagicMock()
    node1.display_url = "https://cdn.instagram.com/img1.jpg"
    node2.display_url = "https://cdn.instagram.com/img2.jpg"

    mock_post = MagicMock()
    mock_post.typename = "GraphSidecar"
    mock_post.is_video = False
    mock_post.get_sidecar_nodes.return_value = [node1, node2]
    mock_post.owner_username = "carousel_user"
    mock_post.date_utc.strftime.return_value = "2026-04-19"
    mock_post.caption = "A carousel post"

    with patch("ytk.instagram.instaloader") as mock_il:
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.return_value = mock_post
        result = fetch_instagram("https://www.instagram.com/p/CAROUSEL/")

    assert result.images == [
        "https://cdn.instagram.com/img1.jpg",
        "https://cdn.instagram.com/img2.jpg",
    ]


def test_fetch_instagram_reel_downloads_video(tmp_path):
    from ytk.instagram import fetch_instagram

    fake_video = tmp_path / "reel.mp4"
    fake_video.write_bytes(b"fakevideo")

    mock_post = MagicMock()
    mock_post.typename = "GraphVideo"
    mock_post.is_video = True
    mock_post.owner_username = "reeluser"
    mock_post.date_utc.strftime.return_value = "2026-04-19"
    mock_post.caption = "Check this out"

    with patch("ytk.instagram.instaloader") as mock_il, \
         patch("ytk.instagram._download_reel", return_value=fake_video):
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.return_value = mock_post
        result = fetch_instagram("https://www.instagram.com/reel/XYZ/")

    assert result.video_path == fake_video


def test_fetch_instagram_instaloader_error_raises():
    from ytk.instagram import fetch_instagram

    with patch("ytk.instagram.instaloader") as mock_il:
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.side_effect = Exception("Post not found")
        with pytest.raises(ValueError, match="Failed to fetch"):
            fetch_instagram("https://www.instagram.com/p/MISSING/")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_instagram.py -v
```

Expected: `ModuleNotFoundError: No module named 'ytk.instagram'`

- [ ] **Step 3: Create `ytk/instagram.py`**

```python
"""Instagram media fetcher using instaloader (public posts only, no auth)."""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import instaloader


@dataclass
class InstagramPost:
    url: str
    username: str
    timestamp: str              # YYYY-MM-DD
    caption: str
    images: list[str] = field(default_factory=list)  # CDN URLs; empty for video-only reels
    video_path: Path | None = None                   # temp .mp4; caller must unlink


def fetch_instagram(url: str) -> InstagramPost:
    """Fetch an Instagram post's media and metadata via instaloader.

    Public posts only — no authentication required.
    For reels, the video is downloaded to a temp file via yt-dlp.
    Caller is responsible for unlinking video_path if set.
    Raises ValueError if the post cannot be fetched.
    """
    L = instaloader.Instaloader(download_pictures=False, download_videos=False, quiet=True)
    shortcode = _extract_shortcode(url)

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
    except Exception as exc:
        raise ValueError(f"Failed to fetch Instagram post {shortcode!r}: {exc}") from exc

    images: list[str] = []
    if post.typename == "GraphSidecar":
        images = [node.display_url for node in post.get_sidecar_nodes()]
    elif post.typename in ("GraphImage", "XDTGraphImage"):
        images = [post.url]

    video_path: Path | None = None
    if post.is_video:
        video_path = _download_reel(url)

    return InstagramPost(
        url=url,
        username=post.owner_username,
        timestamp=post.date_utc.strftime("%Y-%m-%d"),
        caption=post.caption or "",
        images=images,
        video_path=video_path,
    )


def _extract_shortcode(url: str) -> str:
    """Extract the post shortcode from an Instagram post/reel/tv URL."""
    m = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(f"Cannot extract shortcode from URL: {url!r}")
    return m.group(1)


def _download_reel(url: str) -> Path:
    """Download a reel to a temp .mp4 file via yt-dlp. Returns the path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    subprocess.run(
        [
            "yt-dlp", "-f", "bestvideo[ext=mp4]/best[ext=mp4]/best",
            "-o", str(tmp_path), "--no-playlist", url,
        ],
        capture_output=True,
        check=True,
    )
    return tmp_path
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
uv run pytest tests/test_instagram.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add ytk/instagram.py tests/test_instagram.py
git commit -m "feat(instagram): add InstagramPost dataclass and fetch_instagram"
```

---

### Task 4: Modify `ytk/enrich.py` — add `visual_blocks` param

**Files:**
- Modify: `ytk/enrich.py:75-111`
- Create: `tests/test_enrich_visual.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_enrich_visual.py`:

```python
from unittest.mock import patch


def _mock_enrichment():
    from ytk.enrich import Enrichment
    return Enrichment(
        thesis="test thesis",
        summary="test summary",
        key_concepts=["tool: used here"],
        insights=["non-obvious thing"],
        interest_tags=["art"],
        key_moments=[],
    )


def test_enrich_text_only_user_content_is_string():
    from ytk.enrich import enrich

    with patch("ytk.enrich._get_client") as mock_get:
        mock_get.return_value.messages.parse.return_value.parsed_output = _mock_enrichment()
        enrich("transcript text", {"title": "T", "uploader": "U", "duration": 60, "tags": []})

    call_kwargs = mock_get.return_value.messages.parse.call_args.kwargs
    assert isinstance(call_kwargs["messages"][0]["content"], str)


def test_enrich_with_visual_blocks_user_content_is_list():
    from ytk.enrich import enrich

    visual = [{"type": "image", "source": {"type": "url", "url": "https://example.com/img.jpg"}}]
    with patch("ytk.enrich._get_client") as mock_get:
        mock_get.return_value.messages.parse.return_value.parsed_output = _mock_enrichment()
        enrich(
            "caption text",
            {"title": "T", "uploader": "U", "duration": 0, "tags": []},
            visual_blocks=visual,
        )

    call_kwargs = mock_get.return_value.messages.parse.call_args.kwargs
    content = call_kwargs["messages"][0]["content"]
    assert isinstance(content, list)
    assert any(b.get("type") == "image" for b in content)
    assert any(b.get("type") == "text" for b in content)


def test_enrich_visual_system_prompt_includes_image_note():
    from ytk.enrich import enrich

    visual = [{"type": "image", "source": {"type": "url", "url": "https://example.com/img.jpg"}}]
    with patch("ytk.enrich._get_client") as mock_get:
        mock_get.return_value.messages.parse.return_value.parsed_output = _mock_enrichment()
        enrich(
            "caption",
            {"title": "T", "uploader": "U", "duration": 0, "tags": []},
            visual_blocks=visual,
        )

    call_kwargs = mock_get.return_value.messages.parse.call_args.kwargs
    system_text = call_kwargs["system"][0]["text"]
    assert "images" in system_text or "frames" in system_text


def test_enrich_none_visual_blocks_behaves_identically_to_no_arg():
    from ytk.enrich import enrich

    enrichment = _mock_enrichment()
    contents = []
    with patch("ytk.enrich._get_client") as mock_get:
        mock_get.return_value.messages.parse.return_value.parsed_output = enrichment
        enrich("t", {"title": "T", "uploader": "U", "duration": 0, "tags": []})
        contents.append(
            mock_get.return_value.messages.parse.call_args.kwargs["messages"][0]["content"]
        )
        enrich("t", {"title": "T", "uploader": "U", "duration": 0, "tags": []}, visual_blocks=None)
        contents.append(
            mock_get.return_value.messages.parse.call_args.kwargs["messages"][0]["content"]
        )

    assert isinstance(contents[0], str)
    assert isinstance(contents[1], str)
```

- [ ] **Step 2: Run tests to confirm the visual_blocks tests fail**

```bash
uv run pytest tests/test_enrich_visual.py -v
```

Expected: `test_enrich_with_visual_blocks_user_content_is_list` fails — `enrich()` doesn't accept `visual_blocks` yet.

- [ ] **Step 3: Replace the `enrich` function in `ytk/enrich.py`**

Replace lines 75–111 (the entire `enrich` function) with:

```python
def enrich(
    transcript: str,
    metadata: dict,
    visual_blocks: list[dict] | None = None,
) -> Enrichment:
    """
    Send transcript + metadata to Claude Haiku and return structured enrichment.
    Uses prompt caching on the system prompt (stable across all calls).
    When visual_blocks are provided, user content becomes a list interleaving
    text and image blocks for a single-pass multimodal enrichment call.
    """
    client = _get_client()

    chapters_text = ""
    if metadata.get("chapters"):
        lines = [f"  {_fmt_ts(ch['start_time'])} — {ch['title']}" for ch in metadata["chapters"]]
        chapters_text = "\nChapters:\n" + "\n".join(lines)

    text_block = f"""\
Title: {metadata.get("title", "")}
Uploader: {metadata.get("uploader", "")}
Duration: {metadata.get("duration", 0)}s
Tags: {", ".join(metadata.get("tags", [])[:10])}{chapters_text}

Transcript:
{transcript}
"""

    if visual_blocks:
        user_content: str | list = [{"type": "text", "text": text_block}] + visual_blocks
        system_text = (
            _SYSTEM
            + "\nYou may also receive images or video frames — incorporate what you observe "
            "in them into your analysis."
        )
    else:
        user_content = text_block
        system_text = _SYSTEM

    response = client.messages.parse(
        model="claude-haiku-4-5",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        output_format=Enrichment,
    )

    return response.parsed_output
```

- [ ] **Step 4: Run all tests so far**

```bash
uv run pytest tests/test_enrich_visual.py tests/test_vision.py tests/test_instagram.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich.py tests/test_enrich_visual.py
git commit -m "feat(enrich): add visual_blocks param for multimodal enrichment"
```

---

### Task 5: Add `write_instagram_note` to `ytk/vault.py`

**Files:**
- Modify: `ytk/vault.py` (insert after `write_web_note`, around line 272)
- Create: `tests/test_vault_instagram.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_vault_instagram.py`:

```python
def test_write_instagram_note_creates_file(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment, KeyMoment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    post = InstagramPost(
        url="https://www.instagram.com/p/ABC123/",
        username="testuser",
        timestamp="2026-04-19",
        caption="Golden hour vibes in the canyon",
        images=["https://cdn.instagram.com/img.jpg"],
    )
    enrichment = Enrichment(
        thesis="Photographer captures golden hour light through a canyon.",
        summary="A striking image showing warm directional light filtering through sandstone walls.",
        key_concepts=["golden hour: warm diffuse light in the hour after sunrise"],
        insights=["Side lighting reveals texture that flat midday light would hide."],
        interest_tags=["photography", "landscape"],
        key_moments=[KeyMoment(timestamp="img-1", description="main composition")],
    )

    path = write_instagram_note(post, enrichment)

    assert path.exists()
    assert path.parent == tmp_path / "sources" / "instagram"
    content = path.read_text(encoding="utf-8")
    assert "url: https://www.instagram.com/p/ABC123/" in content
    assert "username: testuser" in content
    assert "date: 2026-04-19" in content
    assert "type: instagram" in content
    assert "photography" in content
    assert "golden hour light through a canyon" in content
    assert "img-1" in content
    assert "## Key Moments" in content


def test_write_instagram_note_filename_uses_username_date_slug(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    post = InstagramPost(
        url="https://www.instagram.com/p/XYZ/",
        username="artaccount",
        timestamp="2026-04-19",
        caption="My new painting: abstract blues",
        images=[],
    )
    enrichment = Enrichment(
        thesis="Abstract blue painting.",
        summary="Acrylic on canvas with layered blues.",
        key_concepts=[],
        insights=[],
        interest_tags=["art"],
        key_moments=[],
    )

    path = write_instagram_note(post, enrichment)
    assert path.stem.startswith("artaccount-2026-04-19-")


def test_write_instagram_note_no_moments_omits_section(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    post = InstagramPost(
        url="https://www.instagram.com/p/NM/",
        username="user",
        timestamp="2026-04-19",
        caption="",
        images=[],
    )
    enrichment = Enrichment(
        thesis="t", summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )

    path = write_instagram_note(post, enrichment)
    content = path.read_text(encoding="utf-8")
    assert "## Key Moments" not in content


def test_write_instagram_note_empty_caption_uses_username_fallback(tmp_path, monkeypatch):
    from ytk.instagram import InstagramPost
    from ytk.enrich import Enrichment
    from ytk.vault import write_instagram_note

    monkeypatch.setattr("ytk.vault._get_vault_path", lambda: tmp_path)

    post = InstagramPost(
        url="https://www.instagram.com/reel/ABC/",
        username="reelaccount",
        timestamp="2026-04-19",
        caption="",
        images=[],
    )
    enrichment = Enrichment(
        thesis="t", summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[]
    )

    path = write_instagram_note(post, enrichment)
    assert "reelaccount" in path.stem
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_vault_instagram.py -v
```

Expected: `ImportError: cannot import name 'write_instagram_note' from 'ytk.vault'`

- [ ] **Step 3: Add the import guard and function to `ytk/vault.py`**

At the top of `ytk/vault.py`, after `from .enrich import Enrichment`, add:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .instagram import InstagramPost
```

Then insert the following function after `write_web_note` (after line 272):

```python
def write_instagram_note(post: "InstagramPost", enrichment: Enrichment) -> Path:
    """Write an Obsidian note for an ingested Instagram post. Returns the path written."""
    vault_path = _get_vault_path()
    note_dir = vault_path / "sources" / "instagram"
    note_dir.mkdir(parents=True, exist_ok=True)

    caption_slug = _slug(post.caption[:80]) if post.caption else f"{post.username}-post"
    note_path = note_dir / f"{post.username}-{post.timestamp}-{caption_slug}.md"

    def _normalize_tag(t: str) -> str:
        return re.sub(r"\s+", "-", t.strip().lower())

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)
    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)

    content = (
        f"---\nurl: {post.url}\nusername: {post.username}\ndate: {post.timestamp}\n"
        f"tags:\n{tags_yaml}\ntype: instagram\n---\n\n"
        f"## Thesis\n{enrichment.thesis}\n\n"
        f"## Summary\n{enrichment.summary}\n\n"
        f"## Key Concepts\n{concepts}\n\n"
        f"## Insights\n{insights}\n"
    )
    if enrichment.key_moments:
        moments = "\n".join(
            f"- **{m.timestamp}** — {m.description}" for m in enrichment.key_moments
        )
        content += f"\n## Key Moments\n{moments}\n"

    note_path.write_text(content, encoding="utf-8")
    return note_path
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/test_vault_instagram.py tests/test_enrich_visual.py tests/test_vision.py tests/test_instagram.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ytk/vault.py tests/test_vault_instagram.py
git commit -m "feat(vault): add write_instagram_note for sources/instagram/"
```

---

### Task 6: Add `ytk add-instagram` CLI command

**Files:**
- Modify: `ytk/cli.py` (insert after `ingest` command, ~line 461)

- [ ] **Step 1: Insert the `add-instagram` command into `ytk/cli.py`**

Insert the following block after the `ingest` function (after the blank line following line 460):

```python
@cli.command(name="add-instagram")
@click.argument("url")
def add_instagram(url: str):
    """Fetch an Instagram post, analyze visually with AI, and store in the vault."""
    from .instagram import fetch_instagram
    from .vision import extract_frames, image_blocks
    from .enrich import enrich
    from .vault import write_instagram_note
    from .store import strip_frontmatter, upsert_doc

    with console.status("[bold cyan]Fetching Instagram post...[/]"):
        try:
            post = fetch_instagram(url)
        except ValueError as exc:
            console.print(f"[red]Fetch failed:[/] {exc}")
            raise SystemExit(1)

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", no_wrap=True)
    info.add_column()
    info.add_row("Username", f"@{post.username}")
    info.add_row("Date", post.timestamp)
    if post.images:
        info.add_row("Images", str(len(post.images)))
    if post.video_path:
        info.add_row("Reel", "yes")
    if post.caption:
        info.add_row("Caption", post.caption[:120])
    console.print(Panel(info, title="[bold]Instagram Post[/]", box=box.ROUNDED))

    with console.status("[bold cyan]Preparing visual content...[/]"):
        blocks = image_blocks(urls=post.images or None)
        if post.video_path:
            frame_bytes = extract_frames(post.video_path, timestamps=[], baseline_n=4)
            blocks += image_blocks(frame_bytes=frame_bytes)
            post.video_path.unlink(missing_ok=True)

    meta = {
        "title": post.caption[:120] if post.caption else f"@{post.username}",
        "uploader": post.username,
        "duration": 0,
        "tags": [],
    }

    with console.status("[bold cyan]Enriching with Claude Haiku...[/]"):
        result = enrich(post.caption, meta, visual_blocks=blocks or None)

    console.print(Panel(f"[italic]{result.thesis}[/]", title="[bold]Thesis[/]", box=box.ROUNDED))
    console.print(Panel(result.summary, title="[bold]Summary[/]", box=box.ROUNDED))

    grid = Table.grid(padding=(0, 4))
    grid.add_column()
    grid.add_column()
    concepts = "\n".join(f"[cyan]•[/] {c}" for c in result.key_concepts)
    tags = " ".join(f"[bold cyan]#{t}[/]" for t in result.interest_tags)
    grid.add_row(concepts, tags)
    console.print(Panel(grid, title="[bold]Key Concepts & Tags[/]", box=box.ROUNDED))

    insights = "\n".join(f"[yellow]>[/] {i}" for i in result.insights)
    console.print(Panel(insights, title="[bold]Insights[/]", box=box.ROUNDED))

    try:
        note_path = write_instagram_note(post, result)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        doc_id = "instagram_" + re.sub(r"[^a-zA-Z0-9_-]", "_", note_path.stem[:60])
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(doc_id, body, {
            "doc_id": doc_id,
            "tags": ", ".join(result.interest_tags),
            "source_path": str(note_path),
        })
    except EnvironmentError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")
```

- [ ] **Step 2: Verify the command is registered**

```bash
uv run ytk --help
```

Expected: `add-instagram` appears in the command list alongside `add`, `ingest`, etc.

- [ ] **Step 3: Verify help text**

```bash
uv run ytk add-instagram --help
```

Expected:
```
Usage: ytk add-instagram [OPTIONS] URL

  Fetch an Instagram post, analyze visually with AI, and store in the vault.

Arguments:
  URL  [required]
```

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all existing tests plus new tests pass. No regressions.

- [ ] **Step 5: Commit**

```bash
git add ytk/cli.py
git commit -m "feat(cli): add ytk add-instagram command"
```

---

### Task 7: Extend `ytk add` with YouTube visual analysis

**Files:**
- Modify: `ytk/cli.py:83-188` (`add` command)

- [ ] **Step 1: Replace the AI enrichment section in the `add` command**

In `ytk/cli.py`, the `add` command currently calls `enrich(full_text, meta)` at line ~143. Replace the enrichment block and write-vault block with the following (everything from the `# --- AI enrichment ---` comment through the `upsert` call):

```python
    # --- visual frame extraction ---
    with console.status("[bold cyan]Downloading video for frame extraction...[/]"):
        try:
            from .vision import download_video_temp, extract_frames, hint_detect, image_blocks
            hint_ts = hint_detect(segments)
            video_tmp = download_video_temp(url)
            frame_bytes = extract_frames(video_tmp, hint_ts, baseline_n=4)
            video_tmp.unlink(missing_ok=True)
            visual_blocks = image_blocks(frame_bytes=frame_bytes) if frame_bytes else None
        except Exception:
            visual_blocks = None

    # --- AI enrichment ---
    with console.status("[bold cyan]Enriching with Claude Haiku...[/]"):
        result = enrich(full_text, meta, visual_blocks=visual_blocks)
```

The rest of the `add` command (post-enrichment filter, display, vault write, upsert) remains unchanged.

- [ ] **Step 2: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass. The `add` command change has no unit test (it exercises integration paths — manual smoke test is the verification).

- [ ] **Step 3: Smoke test the `add` command help**

```bash
uv run ytk add --help
```

Expected: command still shows correctly with no import errors.

- [ ] **Step 4: Commit**

```bash
git add ytk/cli.py
git commit -m "feat(cli): wire visual frame extraction into ytk add for YouTube videos"
```

---

## Spec Coverage

| Spec requirement | Task |
|-----------------|------|
| `ytk/vision.py`: `hint_detect`, `extract_frames`, `image_blocks` | Task 2 |
| `ytk/instagram.py`: `InstagramPost`, `fetch_instagram`, shortcode extraction | Task 3 |
| instaloader for images/carousels; yt-dlp for reels | Task 3 |
| `enrich.py` `visual_blocks` param; interleaved content list | Task 4 |
| System prompt visual addendum when visual_blocks present | Task 4 |
| `vault.py` `write_instagram_note` → `sources/instagram/` | Task 5 |
| `ytk add-instagram <url>` end-to-end command | Task 6 |
| `instaloader>=4.10` in pyproject.toml | Task 1 |
| Error: Instagram fetch fails → clear error + exit 1 | Task 6 |
| Error: image URL fails → skip, continue | Task 2 (`image_blocks`) |
| Error: ffmpeg missing → empty frames list | Task 2 (`extract_frames`) |
| Error: Haiku hint call fails → empty list fallback | Task 2 (`hint_detect`) |
| ChromaDB upsert after vault write | Task 6 |
| YouTube `add` extended with visual frame extraction | Task 7 |
