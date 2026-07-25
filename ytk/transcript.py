"""Fetch transcript with youtube-transcript-api primary, faster-whisper fallback."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from youtube_transcript_api import (
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

_AUDIO_CACHE = Path.home() / ".ytk" / "audio"


def prune_audio_cache(
    max_age_days: int,
    *,
    cache_dir: Path | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> list[Path]:
    """Delete top-level ``yt_*`` transcription-cache files older than the cutoff.

    Only the YouTube audio cache that ``_download_audio`` writes directly into the
    cache root is touched. Anything in a subdirectory (voice memos in ``memos/``,
    snaps in ``snaps/``) is never matched — the glob is non-recursive and filtered
    to regular files, so subdir contents are structurally out of reach. A
    non-positive ``max_age_days`` is treated as a no-op rather than a cutoff of
    "now" that would wipe the whole cache. Returns the paths pruned (or that would
    be pruned, under ``dry_run``).
    """
    from datetime import datetime as _dt

    if max_age_days <= 0:
        return []
    root = cache_dir if cache_dir is not None else _AUDIO_CACHE
    if not root.exists():
        return []
    cutoff = (now or _dt.now()).timestamp() - max_age_days * 86400
    pruned: list[Path] = []
    for f in sorted(root.glob("yt_*")):
        st = f.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_mtime >= cutoff:
            continue
        pruned.append(f)
        if not dry_run:
            f.unlink()
    return pruned


def _video_id(url: str) -> str:
    """Extract the 11-char video ID from a YouTube URL."""
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url)
    if not match:
        raise ValueError(f"Could not extract video ID from URL: {url}")
    return match.group(1)


def _fetch_via_api(video_id: str) -> tuple[list[dict], str]:
    """Try youtube-transcript-api. Returns (segments, source_label)."""
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)
    try:
        transcript = transcript_list.find_manually_created_transcript(["en"])
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(["en"])
    segments = transcript.fetch()
    return [
        {"start": s.start, "duration": s.duration, "text": s.text} for s in segments
    ], "youtube-transcript-api"


def _download_audio(url: str) -> Path:
    """Download audio-only stream from a YouTube URL via yt-dlp. Caches by URL hash."""
    import yt_dlp

    _AUDIO_CACHE.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha1(url.encode()).hexdigest()[:12]

    for ext in (".m4a", ".opus", ".mp3", ".ogg", ".wav", ".webm"):
        candidate = _AUDIO_CACHE / f"yt_{url_hash}{ext}"
        if candidate.exists():
            # Refresh mtime so age-based pruning (ytk gc --prune-audio) treats a
            # reused file as recently active instead of deleting it under you.
            os.utime(candidate, None)
            return candidate

    out_template = str(_AUDIO_CACHE / f"yt_{url_hash}.%(ext)s")
    opts: dict[str, object] = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:  # type: ignore[reportArgumentType]  # stub's _Params rejects a plain options dict
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


def _has_audio_stream(media_path: Path) -> bool:
    """Return False only when a valid media container has no audio stream.

    faster-whisper's decoder can raise an opaque ``tuple index out of range``
    for video-only MP4s. PyAV is already a faster-whisper dependency, so inspect
    the container first. If probing itself fails, let Whisper handle the file
    and report its real decoder error instead of misclassifying it as silent.
    """
    try:
        import av

        with av.open(str(media_path)) as container:
            return bool(container.streams.audio)
    except Exception:
        return True


@dataclass
class TranscriptionResult:
    """Outcome of transcribing a local media file.

    status distinguishes an empty-but-successful run ("no_speech") from a
    broken one ("failed") so callers can report capture health truthfully.
    """

    segments: list[dict]  # [{start, duration, text}]
    status: str  # ok | no_speech | failed
    error: str | None = None


def transcribe_file(media_path: Path, whisper_model: str = "base") -> TranscriptionResult:
    """Transcribe an already-downloaded audio/video file with faster-whisper.

    Never downloads anything and never raises: media supplied by any ingest
    pipeline (Instagram reel MP4, TikTok audio) is transcribed in place.
    """
    try:
        if not Path(media_path).is_file():
            raise FileNotFoundError(f"media file not found: {media_path}")
        if not _has_audio_stream(media_path):
            return TranscriptionResult(segments=[], status="no_speech")
        model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
        raw_segments, _ = model.transcribe(str(media_path), beam_size=5)
        segments = [
            {
                "start": seg.start,
                "duration": round(seg.end - seg.start, 3),
                "text": seg.text.strip(),
            }
            for seg in raw_segments
            if seg.text.strip()
        ]
    except Exception as exc:
        return TranscriptionResult(segments=[], status="failed", error=str(exc))
    if not segments:
        return TranscriptionResult(segments=[], status="no_speech")
    return TranscriptionResult(segments=segments, status="ok")


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
    except (NoTranscriptFound, TranscriptsDisabled, RequestBlocked):
        return _fetch_via_whisper(url, whisper_model=whisper_model)


def segments_to_text(segments: list[dict]) -> str:
    """Join transcript segments into a single readable string."""
    return " ".join(s["text"] for s in segments)
