"""TikTok ingestion via yt-dlp (metadata + video) and faster-whisper (audio)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp


@dataclass
class TikTokPost:
    url: str
    video_id: str
    username: str
    timestamp: str               # YYYY-MM-DD
    title: str
    description: str
    duration: int                # seconds
    thumbnail_url: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    music: str | None = None
    tags: list[str] = field(default_factory=list)


_VIDEO_URL_RE = re.compile(
    r"tiktok\.com/(?:@[^/]+/video|t|v)/(\d+|[A-Za-z0-9]+)"
)


def fetch_tiktok(url: str) -> TikTokPost:
    """Fetch TikTok metadata via yt-dlp (no download).

    Resolves shortlinks (vm.tiktok.com / tiktok.com/t/...) to the canonical
    video automatically. Raises ValueError on extraction failure.
    """
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise ValueError(f"yt-dlp failed to extract TikTok URL {url!r}: {exc}") from exc

    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    upload_date = info.get("upload_date", "") or ""
    timestamp = (
        f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
        if len(upload_date) == 8 else ""
    )

    artists = info.get("artists") or []
    track = info.get("track") or info.get("album") or ""
    music = None
    if track and artists:
        music = f"{track} — {', '.join(artists)}"
    elif track:
        music = track

    return TikTokPost(
        url=info.get("webpage_url") or url,
        video_id=str(info.get("id", "")),
        username=info.get("uploader") or info.get("channel") or "",
        timestamp=timestamp,
        title=info.get("title") or "",
        description=info.get("description") or "",
        duration=int(info.get("duration") or 0),
        thumbnail_url=info.get("thumbnail"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        music=music,
        tags=info.get("tags") or [],
    )


def transcribe_tiktok(url: str, whisper_model: str = "base") -> list[dict]:
    """Download audio and transcribe with faster-whisper. Returns timestamped segments.

    Returns [] if transcription fails or audio is too short.
    """
    from .transcript import _download_audio, WhisperModel
    try:
        audio_path = _download_audio(url)
    except Exception:
        return []
    try:
        model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
        raw_segments, _ = model.transcribe(str(audio_path), beam_size=5)
        return [
            {"start": seg.start, "duration": round(seg.end - seg.start, 3), "text": seg.text.strip()}
            for seg in raw_segments
            if seg.text.strip()
        ]
    except Exception:
        return []
