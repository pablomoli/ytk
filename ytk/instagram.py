"""Instagram media fetcher: authenticated via instagrapi when INSTAGRAM_SESSIONID
is set, else anonymous instaloader (which Instagram now often 403s)."""
from __future__ import annotations

import os
import re
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
    if media.media_type == 8:  # album / sidecar
        images = [str(r.thumbnail_url) for r in media.resources if r.thumbnail_url]
    elif media.media_type == 1 and media.thumbnail_url:  # single photo
        images = [str(media.thumbnail_url)]

    video_path: Path | None = None
    if media.media_type == 2 and media.video_url:  # video / reel
        video_path = _download_url_to_temp(str(media.video_url))

    return InstagramPost(
        url=url,
        username=media.user.username,
        timestamp=media.taken_at.strftime("%Y-%m-%d"),
        caption=media.caption_text or "",
        images=images,
        video_path=video_path,
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
        raise ValueError(f"Failed to download video {url!r}: {exc}") from exc
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
    if post.typename in ("GraphSidecar", "XDTGraphSidecar"):
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
    """Download a reel to a temp .mp4 via yt-dlp. Returns the path. Caller must unlink."""
    from .vision import download_video_temp
    try:
        return download_video_temp(url)
    except Exception as exc:
        raise ValueError(f"yt-dlp failed to download reel {url!r}: {exc}") from exc
