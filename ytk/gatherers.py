# pyright: basic
# Composition over legacy basic-mode fetchers (#122): their bare dict/list
# signatures propagate Unknown; goes strict when they do.
"""Per-source evidence gatherers (#197 P2).

Thin composition over the existing fetchers; each returns an EvidenceBundle
with the quality flags filled. Registered into evidence.GATHERERS at import.
Network and whisper work happens here — callers stub these in tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .evidence import GATHERERS, EvidenceBundle, evidence_dir, strip_boilerplate
from .ingest import fetch_web
from .instagram import capture_reel_media, fetch_instagram
from .metadata import fetch_metadata
from .tiktok import fetch_tiktok, transcribe_tiktok
from .transcript import fetch_transcript_evidence
from .vision import hint_detect


def _save_frames(url: str, frame_bytes: list[bytes]) -> list[str]:
    if not frame_bytes:
        return []
    key = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
    frames_dir = evidence_dir() / "frames" / key
    frames_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, data in enumerate(frame_bytes):
        p = frames_dir / f"frame-{i}.jpg"
        p.write_bytes(data)
        paths.append(str(p))
    return paths


def gather_youtube(url: str, title: str | None) -> EvidenceBundle:
    meta: dict[str, Any] = fetch_metadata(url)
    ev = fetch_transcript_evidence(url)
    gaps: list[str] = []
    frames: list[str] = []
    # Frame extraction needs a video download; deferred to a retry sweep or
    # the enricher's request rather than paid on every read. Recorded as a gap
    # so the gate and the enricher know what was not seen.
    if ev.segments and hint_detect(ev.segments):
        gaps.append("visual cues detected but frames not extracted at read time")
    return EvidenceBundle(
        source="youtube",
        url=url,
        title=meta.get("title") or title,
        transcript=ev.segments,
        transcript_origin=ev.origin,
        transcript_language=ev.language,
        transcript_status=ev.status,
        description=meta.get("description"),
        frames=frames,
        gaps=gaps,
        media_id=meta.get("id") or None,
        uploader=meta.get("uploader") or None,
        upload_date=meta.get("upload_date") or None,
        duration=meta.get("duration") or None,
        thumbnail=meta.get("thumbnail") or None,
        chapters=meta.get("chapters") or [],
    )


def _download_image(url: str, dest: Path) -> Path:
    import requests

    with requests.get(url, timeout=30) as resp:
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return dest


def _save_images(post_url: str, image_urls: list[str], gaps: list[str]) -> list[str]:
    """Download CDN image URLs to local evidence files. The note writer embeds
    only local files (vault assets are copies, never hotlinks); a URL left in
    frames is silently dropped at landing, so failures go to gaps instead."""
    if not image_urls:
        return []
    key = hashlib.sha1(post_url.encode(), usedforsecurity=False).hexdigest()[:12]
    img_dir = evidence_dir() / "frames" / key
    img_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, src in enumerate(image_urls):
        dest = img_dir / f"img-{i}.jpg"
        try:
            _download_image(src, dest)
            paths.append(str(dest))
        except Exception as exc:
            gaps.append(f"image download failed: {exc}")
    return paths


def _save_thumbnail(post_url: str, thumb_url: str | None, gaps: list[str]) -> str | None:
    """Instagram CDN URLs expire within days; a hotlinked cover goes blank
    on every surface that renders it later. Download at read time; on
    failure fall back to the URL (better briefly than never)."""
    if not thumb_url:
        return None
    from .evidence import thumbs_dir

    key = hashlib.sha1(post_url.encode(), usedforsecurity=False).hexdigest()[:12]
    dest = thumbs_dir() / f"{key}.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        _download_image(thumb_url, dest)
        return str(dest)
    except Exception as exc:
        gaps.append(f"thumbnail download failed: {exc}")
        return thumb_url


def gather_instagram(url: str, title: str | None) -> EvidenceBundle:
    post = fetch_instagram(url)
    frames: list[str] = []
    segments: list[dict[str, Any]] = []
    status = "none"
    origin = "none"
    gaps: list[str] = []
    if post.video_path is not None:
        cap = capture_reel_media(post)
        frames = _save_frames(url, cap.frame_bytes)
        segments = cap.transcript_segments
        status = cap.transcript_status
        origin = "whisper" if segments else "none"
        gaps.extend(cap.warnings)
    frames += _save_images(url, list(post.images), gaps)
    thumbnail = _save_thumbnail(
        url, post.thumbnail_url or (post.images[0] if post.images else None), gaps
    )
    return EvidenceBundle(
        source="instagram",
        url=url,
        title=title or post.username,
        transcript=segments,
        transcript_origin=origin,
        transcript_language=None,
        transcript_status=status,
        caption=post.caption,
        frames=frames,
        thumbnail=thumbnail,
        gaps=gaps,
    )


def gather_web(url: str, title: str | None) -> EvidenceBundle:
    content = fetch_web(url)
    text, dropped = strip_boilerplate(content.text)
    gaps = [f"boilerplate stripped: {len(dropped)} lines"] if dropped else []
    return EvidenceBundle(
        source="web",
        url=url,
        title=content.title or title,
        transcript=[],
        transcript_origin="none",
        transcript_language=None,
        transcript_status="none",
        text=text,
        gaps=gaps,
    )


def gather_tiktok(url: str, title: str | None) -> EvidenceBundle:
    post = fetch_tiktok(url)
    segments = transcribe_tiktok(url)
    return EvidenceBundle(
        source="tiktok",
        url=url,
        title=post.title or title,
        transcript=segments,
        transcript_origin="whisper" if segments else "none",
        transcript_language=None,
        transcript_status="ok" if segments else "no_speech",
        description=post.description,
        frames=[post.thumbnail_url] if post.thumbnail_url else [],
    )


def gather_reddit(url: str, title: str | None) -> EvidenceBundle:
    from .reddit_feed import (
        build_content_block,
        fetch_comments,
        fetch_post,
        reddit_cookie_header,
        top_comments,
    )

    cookie = reddit_cookie_header()
    post: dict[str, Any] = fetch_post(url, cookie)
    comments = fetch_comments(post["permalink"], cookie)
    block = build_content_block(post, top_comments(comments))
    return EvidenceBundle(
        source="reddit",
        url=url,
        title=post.get("title") or title,
        transcript=[],
        transcript_origin="none",
        transcript_language=None,
        transcript_status="none",
        text=block,
    )


def gather_pinterest(url: str, title: str | None) -> EvidenceBundle:
    from .pinterest import fetch_pinterest

    pin = fetch_pinterest(url)
    return EvidenceBundle(
        source="pinterest",
        url=url,
        title=pin.title or title,
        transcript=[],
        transcript_origin="none",
        transcript_language=None,
        transcript_status="none",
        description=pin.description,
        frames=[pin.image_url] if pin.image_url else [],
    )


GATHERERS.update(
    {
        "youtube": gather_youtube,
        "instagram": gather_instagram,
        "web": gather_web,
        "tiktok": gather_tiktok,
        "reddit": gather_reddit,
        "pinterest": gather_pinterest,
    }
)
