# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Visual analysis primitives: hint detection, frame extraction, image blocks."""

from __future__ import annotations

import base64
import io
import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .sdk import run_structured

_VISUAL_CUE_PHRASES = [
    "as you can see",
    "on screen",
    "in this diagram",
    "let me show",
    "the code here",
    "look at this",
    "over here",
    "in the image",
    "on the left",
    "on the right",
    "shown here",
    "displayed here",
    "in this chart",
    "in this graph",
    "in the terminal",
    "in the output",
]


def hint_detect(segments: list[dict]) -> list[float]:
    """Return timestamps (seconds) where visual content matters.

    Heuristic scan first — if no cue phrases match, the Haiku call is skipped entirely.
    When phrases are found, Haiku also catches implicit visual moments (live demos, etc.).
    """
    full_text = " ".join(s.get("text", "") for s in segments).lower()
    if not any(phrase in full_text for phrase in _VISUAL_CUE_PHRASES):
        return []

    transcript_with_ts = "\n".join(f"[{s['start']:.1f}s] {s.get('text', '')}" for s in segments)
    transcript_with_ts = transcript_with_ts[:30000]

    system = (
        "Identify timestamps (in seconds) where visual content is important in a transcript. "
        "Include on-screen references, code demos, tool demonstrations, and 'let me show you' "
        "moments. Return a JSON object matching the provided schema."
    )
    schema = {
        "type": "object",
        "properties": {
            "timestamps": {
                "type": "array",
                "items": {"type": "number"},
            }
        },
        "required": ["timestamps"],
    }

    try:
        data = run_structured(system, f"Transcript:\n{transcript_with_ts}", schema)
    except Exception:
        return []

    timestamps = data.get("timestamps", [])
    if not isinstance(timestamps, list):
        return []
    return sorted({float(t) for t in timestamps if isinstance(t, (int, float))})


# launchd strips PATH to /usr/bin:/bin:/usr/sbin:/sbin, so the hub process
# (where the loop reads) cannot see homebrew's ffmpeg/ffprobe by bare name.
_TOOL_DIRS = (Path("/opt/homebrew/bin"), Path("/usr/local/bin"))


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for d in _TOOL_DIRS:
        candidate = d / name
        if candidate.is_file():
            return str(candidate)
    return name


def probe_duration(video_path: Path) -> float | None:
    """Probe a video's duration in seconds via ffprobe. None if probing fails."""
    try:
        probe = subprocess.run(
            [
                _tool("ffprobe"),
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(json.loads(probe.stdout)["format"]["duration"])
    except (subprocess.CalledProcessError, KeyError, ValueError, FileNotFoundError):
        return None


def extract_frames(
    video_path: Path,
    timestamps: list[float],
    baseline_n: int = 4,
) -> list[bytes]:
    """Extract JPEG frames at hint timestamps plus evenly-spaced baseline frames.

    Returns raw JPEG bytes. Returns [] silently if ffmpeg/ffprobe is not installed.
    """
    duration = probe_duration(video_path)
    if duration is None:
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
                    _tool("ffmpeg"),
                    "-v",
                    "quiet",
                    "-ss",
                    str(ts),
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-f",
                    "image2",
                    str(tmp_path),
                    "-y",
                ],
                capture_output=True,
                check=True,
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
    force_base64: bool = False,
) -> list[dict]:
    """Build Anthropic API content blocks from CDN image URLs or raw JPEG bytes.

    For URLs: tries a URL-type block first (CDN URLs are valid at ingest time).
    Falls back to downloading and base64-encoding if the HEAD check fails.
    Pass force_base64=True to always download (e.g. Instagram CDN, which returns
    200 on HEAD but is blocked by robots.txt when Claude fetches it directly).
    Silently skips images that cannot be loaded.
    """
    from urllib.parse import urlparse

    blocks: list[dict] = []

    for url in urls or []:
        if urlparse(url).scheme not in ("http", "https"):
            continue
        if not force_base64:
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
            blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                }
            )
        except Exception:
            pass

    for raw in frame_bytes or []:
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(raw).decode(),
                },
            }
        )

    return blocks


def download_video_temp(url: str) -> Path:
    """Download a video stream to a temp .mp4 file via yt-dlp. Caller must unlink.

    yt-dlp treats any pre-existing destination as already-downloaded, so we
    reserve a unique path without creating the file.
    """
    fd, tmp_name = tempfile.mkstemp(suffix=".mp4")
    import os as _os

    _os.close(fd)
    _os.unlink(tmp_name)
    tmp_path = Path(tmp_name)
    try:
        subprocess.run(
            [
                "yt-dlp",
                "-f",
                "bestvideo[ext=mp4]/best[ext=mp4]/best",
                "-o",
                str(tmp_path),
                "--no-playlist",
                url,
            ],
            capture_output=True,
            check=True,
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path


# ---------------------------------------------------------------------------
# The dense frame tier and the contact sheet (#202)
# ---------------------------------------------------------------------------

# One ruler per medium (footage-first method, section 11): time for reels,
# picture change for anything the time ruler would overrun.
DENSE_EVERY_S = 2.0
FRAME_CAP = 60
# ffmpeg scene score above which a frame counts as a cut.
SCENE_THRESHOLD = 0.3
# Fewer cuts than this on a long item means a talk, not a screencast.
TALK_MIN_CUTS = 8
TALK_FRAMES = 12
TIER_WIDTH = 720


@dataclass(frozen=True)
class FramePlan:
    ruler: str  # time | scene
    every_s: float
    cap: int


@dataclass(frozen=True)
class TimedFrame:
    t: float
    data: bytes


def frame_plan(duration: float | None) -> FramePlan:
    """Time ruler while it fits under the cap; past that the picture decides."""
    if duration is None or duration <= DENSE_EVERY_S * FRAME_CAP:
        return FramePlan(ruler="time", every_s=DENSE_EVERY_S, cap=FRAME_CAP)
    return FramePlan(ruler="scene", every_s=DENSE_EVERY_S, cap=FRAME_CAP)


def nearest_frames(frames: list[TimedFrame], timestamps: list[float]) -> list[TimedFrame]:
    """One tier frame per timestamp, closest wins, duplicates dropped in order."""
    if not frames:
        return []
    picked: list[TimedFrame] = []
    for ts in timestamps:
        best = min(frames, key=lambda f: abs(f.t - ts))
        if best not in picked:
            picked.append(best)
    return picked


def _frames_from_dir(out_dir: Path, times: list[float]) -> list[TimedFrame]:
    files = sorted(out_dir.glob("f-*.jpg"))
    return [TimedFrame(t=t, data=f.read_bytes()) for f, t in zip(files, times, strict=False)]


def _time_pass(video_path: Path, every_s: float, width: int) -> list[TimedFrame]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        subprocess.run(
            [
                _tool("ffmpeg"),
                "-v",
                "error",
                "-i",
                str(video_path),
                "-vf",
                f"fps=1/{every_s},scale='min({width},iw)':-2",
                "-q:v",
                "3",
                str(out / "f-%03d.jpg"),
            ],
            capture_output=True,
            check=True,
        )
        n = len(list(out.glob("f-*.jpg")))
        return _frames_from_dir(out, [i * every_s for i in range(n)])


_PTS = re.compile(r"pts_time:\s*([0-9.]+)")


def _scene_pass(video_path: Path, width: int) -> list[TimedFrame]:
    """Frame 0 plus every frame whose scene score crosses the threshold;
    showinfo on stderr carries the timestamps in output order."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        proc = subprocess.run(
            [
                _tool("ffmpeg"),
                "-v",
                "info",
                "-nostats",
                "-i",
                str(video_path),
                "-vf",
                f"select='eq(n,0)+gt(scene,{SCENE_THRESHOLD})',showinfo,scale='min({width},iw)':-2",
                "-fps_mode",
                "vfr",
                "-q:v",
                "3",
                str(out / "f-%03d.jpg"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        times = [float(m) for m in _PTS.findall(proc.stderr)]
        return _frames_from_dir(out, times)


def _thin(frames: list[TimedFrame], cap: int) -> list[TimedFrame]:
    if len(frames) <= cap:
        return frames
    last = len(frames) - 1
    idx = sorted({round(i * last / (cap - 1)) for i in range(cap)})
    return [frames[i] for i in idx]


def extract_frame_tier(
    video_path: Path, plan: FramePlan, duration: float | None
) -> list[TimedFrame]:
    """One ffmpeg pass under the plan's ruler. Raises on ffmpeg failure so
    the caller can fall back to the sparse path and say so."""
    if plan.ruler == "time":
        return _thin(_time_pass(video_path, plan.every_s, TIER_WIDTH), plan.cap)
    cuts = _scene_pass(video_path, TIER_WIDTH)
    if len(cuts) - 1 >= TALK_MIN_CUTS:
        return _thin(cuts, plan.cap)
    # A talk: two faces and a room. A dozen frames spaced over the length.
    span = duration or (cuts[-1].t if cuts else 0.0)
    if span <= 0:
        return cuts
    return _time_pass(video_path, span / TALK_FRAMES, TIER_WIDTH)[:TALK_FRAMES]


def contact_sheet(
    frames: list[TimedFrame],
    label: str,
    *,
    across: int = 6,
    tile_w: int = 320,
    label_h: int = 18,
    quality: int = 80,
) -> bytes | None:
    """Tile the tier six across with a stamped strip above each frame, so a
    whole item reads in one look and only the sharp frames get opened."""
    if not frames:
        return None
    from PIL import Image, ImageDraw, ImageFont

    tiles: list[Image.Image] = []
    for f in frames:
        im = Image.open(io.BytesIO(f.data)).convert("RGB")
        h = max(1, round(im.height * tile_w / im.width))
        tiles.append(im.resize((tile_w, h)))
    tile_h = max(t.height for t in tiles)
    rows = (len(tiles) + across - 1) // across
    sheet = Image.new("RGB", (across * tile_w, rows * (tile_h + label_h)), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=max(8, label_h - 6))
    except TypeError:  # Pillow < 10.1 has no sized default
        font = ImageFont.load_default()
    for i, (tile, f) in enumerate(zip(tiles, frames, strict=True)):
        x = (i % across) * tile_w
        y = (i // across) * (tile_h + label_h)
        draw.text((x + 4, y + 2), f"{label} t={int(f.t)}s", fill=(255, 255, 255), font=font)
        sheet.paste(tile, (x, y + label_h))
    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
