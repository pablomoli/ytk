"""Fetch transcript with youtube-transcript-api primary, faster-whisper fallback."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

_AUDIO_CACHE = Path.home() / ".ytk" / "audio"


def _video_id(url: str) -> str:
    """Extract the 11-char video ID from a YouTube URL."""
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url)
    if not match:
        raise ValueError(f"Could not extract video ID from URL: {url}")
    return match.group(1)


def _fetch_via_api(video_id: str) -> tuple[list[dict], str]:
    """Try youtube-transcript-api. Returns (segments, source_label)."""
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    try:
        transcript = transcript_list.find_manually_created_transcript(["en"])
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(["en"])
    segments = transcript.fetch()
    return [{"start": s["start"], "duration": s["duration"], "text": s["text"]} for s in segments], "youtube-transcript-api"


def _download_audio(url: str) -> Path:
    """Download audio-only stream from a YouTube URL via yt-dlp. Caches by URL hash."""
    import yt_dlp

    _AUDIO_CACHE.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha1(url.encode()).hexdigest()[:12]

    for ext in (".m4a", ".opus", ".mp3", ".ogg", ".wav", ".webm"):
        candidate = _AUDIO_CACHE / f"yt_{url_hash}{ext}"
        if candidate.exists():
            return candidate

    out_template = str(_AUDIO_CACHE / f"yt_{url_hash}.%(ext)s")
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = info.get("ext", "m4a")
        downloaded = _AUDIO_CACHE / f"yt_{url_hash}.{ext}"
        if not downloaded.exists():
            candidates = list(_AUDIO_CACHE.glob(f"yt_{url_hash}.*"))
            if not candidates:
                raise FileNotFoundError(
                    f"yt-dlp completed but no audio file found for hash {url_hash}"
                )
            downloaded = candidates[0]
    return downloaded


def WhisperModel(model_name: str, **kwargs):
    """Lazy import of faster_whisper.WhisperModel."""
    from faster_whisper import WhisperModel as _WM
    return _WM(model_name, **kwargs)


def _fetch_via_whisper(url: str, whisper_model: str = "base") -> tuple[list[dict], str]:
    """Download audio and transcribe locally with faster-whisper. Preserves timestamps."""
    audio_path = _download_audio(url)
    model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
    raw_segments, _ = model.transcribe(str(audio_path), beam_size=5)
    segments = [
        {"start": seg.start, "duration": round(seg.end - seg.start, 3), "text": seg.text.strip()}
        for seg in raw_segments
        if seg.text.strip()
    ]
    return segments, "whisper"


def fetch_transcript(url: str, whisper_model: str = "base") -> tuple[list[dict], str]:
    """
    Return (segments, source) where segments are [{start, duration, text}].
    Tries youtube-transcript-api first, falls back to faster-whisper local ASR.
    """
    video_id = _video_id(url)
    try:
        return _fetch_via_api(video_id)
    except (NoTranscriptFound, TranscriptsDisabled):
        return _fetch_via_whisper(url, whisper_model=whisper_model)


def segments_to_text(segments: list[dict]) -> str:
    """Join transcript segments into a single readable string."""
    return " ".join(s["text"] for s in segments)
