"""Reel media is identified explicitly at fetch time, never inferred from images."""

from datetime import datetime
from types import SimpleNamespace

import ytk.instagram as instagram_mod
from ytk.instagram import fetch_instagram_auth


class FakeMediaClient:
    def __init__(self, media):
        self._media = media

    def media_pk_from_url(self, url):
        return "12345"

    def media_info(self, pk):
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


def test_single_photo_is_image():
    post = fetch_instagram_auth(
        "https://www.instagram.com/p/abc/", FakeMediaClient(_media())
    )
    assert post.media_kind == "image"


def test_album_is_carousel():
    media = _media(
        media_type=8,
        thumbnail_url=None,
        resources=[SimpleNamespace(thumbnail_url="https://cdn.example/s1.jpg")],
    )
    post = fetch_instagram_auth(
        "https://www.instagram.com/p/abc/", FakeMediaClient(media)
    )
    assert post.media_kind == "carousel"


def test_reel_is_video_even_if_download_fails(monkeypatch, tmp_path):
    """media_kind must come from the API media type, not from whether the
    video download produced a file or from len(images)."""
    monkeypatch.setattr(instagram_mod, "_download_url_to_temp", lambda url: tmp_path / "v.mp4")
    media = _media(
        media_type=2,
        video_url="https://cdn.example/reel.mp4",
        thumbnail_url="https://cdn.example/cover.jpg",
    )
    post = fetch_instagram_auth(
        "https://www.instagram.com/reel/abc/", FakeMediaClient(media)
    )
    assert post.media_kind == "video"

    # video_url missing entirely: still a video, with no video_path
    media_no_url = _media(media_type=2, video_url=None)
    post2 = fetch_instagram_auth(
        "https://www.instagram.com/reel/abc/", FakeMediaClient(media_no_url)
    )
    assert post2.media_kind == "video"
    assert post2.video_path is None


def test_anonymous_video_is_video(monkeypatch, tmp_path):
    fake_post = SimpleNamespace(
        typename="GraphVideo",
        is_video=True,
        owner_username="quirkypobs",
        date_utc=datetime(2026, 7, 1),
        caption="cap",
        url="https://cdn.example/x.jpg",
    )
    monkeypatch.setattr(
        instagram_mod.instaloader.Post, "from_shortcode", lambda ctx, sc: fake_post
    )
    monkeypatch.setattr(instagram_mod, "_download_reel", lambda url: tmp_path / "v.mp4")
    post = instagram_mod._fetch_instagram_anonymous("https://www.instagram.com/reel/abc/")
    assert post.media_kind == "video"


def test_anonymous_sidecar_is_carousel(monkeypatch):
    fake_post = SimpleNamespace(
        typename="GraphSidecar",
        is_video=False,
        owner_username="quirkypobs",
        date_utc=datetime(2026, 7, 1),
        caption="cap",
        get_sidecar_nodes=lambda: [SimpleNamespace(display_url="https://cdn.example/1.jpg")],
    )
    monkeypatch.setattr(
        instagram_mod.instaloader.Post, "from_shortcode", lambda ctx, sc: fake_post
    )
    post = instagram_mod._fetch_instagram_anonymous("https://www.instagram.com/p/abc/")
    assert post.media_kind == "carousel"
