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
    try:
        subprocess.run(
            [
                "yt-dlp", "-f", "bestvideo[ext=mp4]/best[ext=mp4]/best",
                "-o", str(tmp_path), "--no-playlist", url,
            ],
            capture_output=True,
            check=True,
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path
