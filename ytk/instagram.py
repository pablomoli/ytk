# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Instagram media fetcher: authenticated via instagrapi when INSTAGRAM_SESSIONID
is set, else anonymous instaloader (which Instagram now often 403s)."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import instaloader

from .transcript import TranscriptionResult, transcribe_file
from .vision import (
    TimedFrame,
    contact_sheet,
    extract_frame_tier,
    extract_frames,
    frame_plan,
    nearest_frames,
    probe_duration,
)

BASELINE_FRAMES = 4


@dataclass
class InstagramPost:
    url: str
    username: str
    timestamp: str  # YYYY-MM-DD
    caption: str
    images: list[str] = field(default_factory=list)  # CDN URLs; empty for video-only reels
    video_path: Path | None = None  # temp .mp4; caller must unlink
    thumbnail_url: str | None = None  # cover image for video reels
    media_kind: str = "image"  # image | carousel | video — set from the
    # API media type, never from len(images)


@dataclass
class ReelCapture:
    """What was actually recovered from a reel's video, plus every failure."""

    frame_bytes: list[bytes] = field(default_factory=list)  # sparse: what the enricher sees
    dense_frames: list[TimedFrame] = field(default_factory=list)  # the tier (#202)
    sheet_bytes: bytes | None = None
    ruler: str | None = None  # time | scene
    transcript_segments: list[dict] = field(default_factory=list)
    transcript_status: str = "skipped"  # ok | no_speech | failed | skipped
    duration: float | None = None
    warnings: list[str] = field(default_factory=list)


def _baseline_timestamps(duration: float, n: int = BASELINE_FRAMES) -> list[float]:
    return [duration * i / (n + 1) for i in range(1, n + 1)]


def _capture_frames(post: InstagramPost, cap: ReelCapture) -> None:
    """One ffmpeg pass: the dense tier, the sparse baseline picked from it,
    and the contact sheet. The pre-tier path stays as the fallback."""
    assert post.video_path is not None
    plan = frame_plan(cap.duration)
    try:
        tier = extract_frame_tier(post.video_path, plan, cap.duration)
    except Exception as exc:
        cap.warnings.append(f"dense frame tier failed: {exc}")
        tier = []
    if tier:
        cap.dense_frames = tier
        cap.ruler = plan.ruler
        span = cap.duration or tier[-1].t
        cap.frame_bytes = [f.data for f in nearest_frames(tier, _baseline_timestamps(span))]
        try:
            label = _extract_shortcode(post.url)
        except ValueError:
            label = "reel"
        try:
            cap.sheet_bytes = contact_sheet(tier, label=label)
        except Exception as exc:
            cap.warnings.append(f"contact sheet failed: {exc}")
        return
    try:
        cap.frame_bytes = (
            extract_frames(post.video_path, timestamps=[], baseline_n=BASELINE_FRAMES) or []
        )
    except Exception as exc:
        cap.warnings.append(f"frame extraction failed: {exc}")


def capture_reel_media(post: InstagramPost, whisper_model: str = "base") -> ReelCapture:
    """Extract frames and transcribe audio from an already-downloaded reel MP4.

    Degrades gracefully — every failure lands in warnings instead of raising —
    and the temp MP4 is deleted in the outer finally on every path, but only
    after both frame extraction and transcription have had their chance.
    """
    cap = ReelCapture()
    if not post.video_path:
        cap.warnings.append("reel video was not downloaded; frames and transcript unavailable")
        return cap
    try:
        try:
            cap.duration = probe_duration(post.video_path)
        except Exception as exc:
            cap.warnings.append(f"ffprobe failed: {exc}")
        _capture_frames(post, cap)
        if not cap.frame_bytes and not any("frame" in w for w in cap.warnings):
            cap.warnings.append(
                "frame extraction produced 0 frames (ffmpeg/ffprobe missing or failed)"
            )
        try:
            result = transcribe_file(post.video_path, whisper_model=whisper_model)
        except Exception as exc:
            result = TranscriptionResult(segments=[], status="failed", error=str(exc))
        cap.transcript_segments = result.segments
        cap.transcript_status = result.status
        if result.status == "failed":
            cap.warnings.append(f"transcription failed: {result.error}")
    finally:
        post.video_path.unlink(missing_ok=True)
    return cap


def fetch_instagram(url: str) -> InstagramPost:
    """Fetch an Instagram post's media and metadata.

    Uses the authenticated instagrapi client when INSTAGRAM_SESSIONID is set
    (anonymous GraphQL access is now routinely 403'd); otherwise falls back to
    anonymous instaloader. For reels, the video lands in a temp file.
    Caller is responsible for unlinking video_path if set.
    Raises ValueError if the post cannot be fetched.
    """
    sessionid = os.environ.get("INSTAGRAM_SESSIONID", "")
    if sessionid:
        from . import reels

        client = reels.get_client(sessionid)
        return fetch_instagram_auth(url, client)
    return _fetch_instagram_anonymous(url)


def fetch_instagram_auth(url: str, client) -> InstagramPost:
    """Fetch post media and metadata through a logged-in instagrapi client.

    Reel videos are downloaded directly from the CDN URL the API returns,
    bypassing yt-dlp entirely.
    """
    try:
        media = client.media_info(client.media_pk_from_url(url))
    except Exception as exc:
        raise ValueError(f"Failed to fetch Instagram post {url!r}: {exc}") from exc

    images: list[str] = []
    media_kind = {1: "image", 2: "video", 8: "carousel"}.get(media.media_type, "image")
    if media.media_type == 8:  # album / sidecar
        images = [str(r.thumbnail_url) for r in media.resources if r.thumbnail_url]
    elif media.media_type == 1 and media.thumbnail_url:  # single photo
        images = [str(media.thumbnail_url)]

    video_path: Path | None = None
    thumbnail_url: str | None = None
    if media.media_type == 2:  # video / reel
        if media.video_url:
            video_path = _download_url_to_temp(str(media.video_url))
        if media.thumbnail_url:
            thumbnail_url = str(media.thumbnail_url)

    return InstagramPost(
        url=url,
        username=media.user.username,
        timestamp=media.taken_at.strftime("%Y-%m-%d"),
        caption=media.caption_text or "",
        images=images,
        video_path=video_path,
        thumbnail_url=thumbnail_url,
        media_kind=media_kind,
    )


def _download_url_to_temp(url: str) -> Path:
    """Stream a CDN video URL to a temp .mp4. Caller must unlink."""
    import requests

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    try:
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=1 << 20):
                tmp.write(chunk)
    except Exception as exc:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        # deliberately omit the exception detail: requests errors embed the
        # CDN URL, which carries signed access tokens, and this message ends
        # up in CLI output and hub job logs
        raise ValueError(f"Failed to download reel video ({type(exc).__name__})") from exc
    tmp.close()
    return Path(tmp.name)


def _fetch_instagram_anonymous(url: str) -> InstagramPost:
    L = instaloader.Instaloader(download_pictures=False, download_videos=False, quiet=True)
    shortcode = _extract_shortcode(url)

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
    except Exception as exc:
        raise ValueError(f"Failed to fetch Instagram post {shortcode!r}: {exc}") from exc

    images: list[str] = []
    media_kind = "image"
    if post.typename in ("GraphSidecar", "XDTGraphSidecar"):
        images = [node.display_url for node in post.get_sidecar_nodes()]
        media_kind = "carousel"
    elif post.typename in ("GraphImage", "XDTGraphImage"):
        images = [post.url]

    video_path: Path | None = None
    if post.is_video:
        media_kind = "video"
        video_path = _download_reel(url)

    return InstagramPost(
        url=url,
        username=post.owner_username,
        timestamp=post.date_utc.strftime("%Y-%m-%d"),
        caption=post.caption or "",
        images=images,
        video_path=video_path,
        media_kind=media_kind,
    )


def _extract_shortcode(url: str) -> str:
    """Extract the post shortcode from an Instagram post/reel/tv URL."""
    m = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(f"Cannot extract shortcode from URL: {url!r}")
    return m.group(1)


def _download_reel(url: str) -> Path:
    """Download a reel to a temp .mp4 via yt-dlp. Returns the path. Caller must unlink."""
    from .vision import download_video_temp

    try:
        return download_video_temp(url)
    except Exception as exc:
        raise ValueError(f"yt-dlp failed to download reel {url!r}: {exc}") from exc
