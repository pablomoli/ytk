"""Fetch transcript with youtube-transcript-api primary, yt-dlp subtitles fallback."""

from __future__ import annotations

import io
import re

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled


def _video_id(url: str) -> str:
    """Extract the 11-char video ID from a YouTube URL."""
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url)
    if not match:
        raise ValueError(f"Could not extract video ID from URL: {url}")
    return match.group(1)


def _fetch_via_api(video_id: str) -> tuple[list[dict], str]:
    """Try youtube-transcript-api. Returns (segments, source_label)."""
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    # prefer manually created English, fall back to auto-generated
    try:
        transcript = transcript_list.find_manually_created_transcript(["en"])
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(["en"])
    segments = transcript.fetch()
    return [{"start": s["start"], "duration": s["duration"], "text": s["text"]} for s in segments], "youtube-transcript-api"


def _fetch_via_ytdlp(url: str) -> tuple[list[dict], str]:
    """Fallback: download auto-captions via yt-dlp and parse the VTT."""
    buf = io.StringIO()

    class _Sink(io.StringIO):
        pass

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "subtitlesformat": "vtt",
        "outtmpl": "-",          # write to stdout so yt-dlp doesn't create files
    }

    # yt-dlp doesn't give an easy in-memory subtitle path, so write to a temp file
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        opts["outtmpl"] = os.path.join(tmpdir, "sub.%(ext)s")
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        # find the .vtt file written
        vtt_path = None
        for fname in os.listdir(tmpdir):
            if fname.endswith(".vtt"):
                vtt_path = os.path.join(tmpdir, fname)
                break

        if vtt_path is None:
            raise RuntimeError("yt-dlp could not retrieve subtitles for this video.")

        with open(vtt_path, "r", encoding="utf-8") as f:
            vtt_text = f.read()

    return _parse_vtt(vtt_text), "yt-dlp"


def _parse_vtt(vtt: str) -> list[dict]:
    """Parse a WebVTT string into segments [{start, duration, text}]."""
    segments = []
    blocks = re.split(r"\n{2,}", vtt.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        # look for a timing line: 00:00:00.000 --> 00:00:05.000
        timing_line = None
        text_lines = []
        for i, line in enumerate(lines):
            if "-->" in line:
                timing_line = line
                text_lines = lines[i + 1 :]
                break
        if timing_line is None:
            continue
        m = re.match(
            r"(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)\s*-->\s*(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)",
            timing_line,
        )
        if not m:
            continue
        start = _vtt_time_to_seconds(m.group(1))
        end = _vtt_time_to_seconds(m.group(2))
        # strip VTT tags like <c>, <00:00:00.000>
        text = " ".join(re.sub(r"<[^>]+>", "", l) for l in text_lines).strip()
        if text:
            segments.append({"start": start, "duration": round(end - start, 3), "text": text})

    # VTT auto-captions use overlapping sliding windows — deduplicate consecutive identical text.
    deduped = []
    for seg in segments:
        if not deduped or seg["text"] != deduped[-1]["text"]:
            deduped.append(seg)
    return deduped


def _vtt_time_to_seconds(ts: str) -> float:
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    m, s = parts
    return int(m) * 60 + float(s)


def fetch_transcript(url: str) -> tuple[list[dict], str]:
    """
    Return (segments, source) where segments are [{start, duration, text}].
    Tries youtube-transcript-api first, falls back to yt-dlp subtitles.
    """
    video_id = _video_id(url)
    try:
        return _fetch_via_api(video_id)
    except (NoTranscriptFound, TranscriptsDisabled, Exception):
        return _fetch_via_ytdlp(url)


def segments_to_text(segments: list[dict]) -> str:
    """Join transcript segments into a single readable string."""
    return " ".join(s["text"] for s in segments)
