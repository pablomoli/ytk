"""Visual analysis primitives: hint detection, frame extraction, image blocks."""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import anthropic

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


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
    transcript_with_ts = transcript_with_ts[:30000]
    client = _get_client()
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


def _media_type_from_content_type(ct: str) -> str:
    """Map a Content-Type header value to an Anthropic-accepted image media type."""
    ct = ct.lower().split(";")[0].strip()
    return {
        "image/jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "image/png": "image/png",
        "image/gif": "image/gif",
        "image/webp": "image/webp",
    }.get(ct, "image/jpeg")


def image_blocks(
    urls: list[str] | None = None,
    frame_bytes: list[bytes] | None = None,
) -> list[dict]:
    """Build Anthropic API content blocks from CDN image URLs or raw JPEG bytes.

    For URLs: tries a URL-type block first (CDN URLs are valid at ingest time).
    Falls back to downloading and base64-encoding if the HEAD check fails.
    Silently skips images that cannot be loaded.
    """
    from urllib.parse import urlparse
    blocks: list[dict] = []

    for url in (urls or []):
        if urlparse(url).scheme not in ("http", "https"):
            continue
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
                ct = resp.headers.get("Content-Type", "image/jpeg")
                media_type = _media_type_from_content_type(ct)
                data = base64.standard_b64encode(resp.read()).decode()
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
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
    try:
        subprocess.run(
            [
                "yt-dlp", "-f", "bestvideo[ext=mp4]/best[ext=mp4]/best",
                "--no-audio", "-o", str(tmp_path), "--no-playlist", url,
            ],
            capture_output=True,
            check=True,
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path
