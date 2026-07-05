"""Tests for the authenticated (instagrapi) Instagram fetch path."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import ytk.instagram as instagram_mod
from ytk.instagram import fetch_instagram_auth


class FakeMediaClient:
    def __init__(self, media):
        self._media = media
        self.requested_urls = []

    def media_pk_from_url(self, url):
        self.requested_urls.append(url)
        return "12345"

    def media_info(self, pk):
        assert pk == "12345"
        return self._media


def _media(**overrides):
    base = dict(
        media_type=1,
        user=SimpleNamespace(username="quirkypobs"),
        taken_at=datetime(2026, 7, 1, 12, 0),
        caption_text="a caption",
        thumbnail_url="https://cdn.example/photo.jpg",
        video_url=None,
        resources=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_auth_fetch_photo():
    client = FakeMediaClient(_media())
    post = fetch_instagram_auth("https://www.instagram.com/p/abc/", client)
    assert post.username == "quirkypobs"
    assert post.timestamp == "2026-07-01"
    assert post.caption == "a caption"
    assert post.images == ["https://cdn.example/photo.jpg"]
    assert post.video_path is None


def test_auth_fetch_album_collects_resource_thumbnails():
    media = _media(
        media_type=8,
        thumbnail_url=None,
        resources=[
            SimpleNamespace(thumbnail_url="https://cdn.example/s1.jpg"),
            SimpleNamespace(thumbnail_url="https://cdn.example/s2.jpg"),
        ],
    )
    post = fetch_instagram_auth("https://www.instagram.com/p/abc/", FakeMediaClient(media))
    assert post.images == ["https://cdn.example/s1.jpg", "https://cdn.example/s2.jpg"]


def test_auth_fetch_reel_downloads_video_from_cdn(monkeypatch, tmp_path):
    downloaded = []

    def fake_download(url):
        downloaded.append(url)
        return tmp_path / "reel.mp4"

    monkeypatch.setattr(instagram_mod, "_download_url_to_temp", fake_download)
    media = _media(
        media_type=2,
        thumbnail_url="https://cdn.example/cover.jpg",
        video_url="https://cdn.example/reel.mp4?sig=x",
        caption_text=None,
    )
    post = fetch_instagram_auth(
        "https://www.instagram.com/reel/abc/", FakeMediaClient(media)
    )
    assert downloaded == ["https://cdn.example/reel.mp4?sig=x"]
    assert post.video_path == tmp_path / "reel.mp4"
    assert post.images == []
    assert post.caption == ""


def test_fetch_instagram_dispatches_to_auth_when_sessionid(monkeypatch):
    import ytk.reels as reels_mod

    monkeypatch.setenv("INSTAGRAM_SESSIONID", "sess-123")
    client = FakeMediaClient(_media())
    monkeypatch.setattr(reels_mod, "get_client", lambda sessionid: client)

    post = instagram_mod.fetch_instagram("https://www.instagram.com/p/abc/")
    assert post.username == "quirkypobs"
    assert client.requested_urls == ["https://www.instagram.com/p/abc/"]
