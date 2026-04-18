"""Fetch video metadata via yt-dlp's Python API."""

from __future__ import annotations

import yt_dlp


def fetch_metadata(url: str) -> dict:
    """Return a dict with title, description, duration, chapters, tags, upload_date, uploader."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "id": info.get("id", ""),
        "url": url,
        "title": info.get("title", ""),
        "uploader": info.get("uploader", ""),
        "upload_date": info.get("upload_date", ""),  # YYYYMMDD
        "duration": info.get("duration", 0),          # seconds
        "description": info.get("description", ""),
        "tags": info.get("tags") or [],
        "chapters": [
            {
                "start_time": ch.get("start_time"),
                "title": ch.get("title", ""),
            }
            for ch in (info.get("chapters") or [])
        ],
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "thumbnail": info.get("thumbnail", ""),
    }
