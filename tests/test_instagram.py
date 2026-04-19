from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def test_extract_shortcode_post():
    from ytk.instagram import _extract_shortcode
    assert _extract_shortcode("https://www.instagram.com/p/ABC123xyz/") == "ABC123xyz"


def test_extract_shortcode_reel():
    from ytk.instagram import _extract_shortcode
    assert _extract_shortcode("https://www.instagram.com/reel/DEF456abc/") == "DEF456abc"


def test_extract_shortcode_tv():
    from ytk.instagram import _extract_shortcode
    assert _extract_shortcode("https://www.instagram.com/tv/GHI789/") == "GHI789"


def test_extract_shortcode_invalid_raises():
    from ytk.instagram import _extract_shortcode
    with pytest.raises(ValueError, match="Cannot extract shortcode"):
        _extract_shortcode("https://www.instagram.com/explore/tags/art/")


def test_fetch_instagram_single_image():
    from ytk.instagram import fetch_instagram, InstagramPost

    mock_post = MagicMock()
    mock_post.typename = "GraphImage"
    mock_post.url = "https://cdn.instagram.com/image.jpg"
    mock_post.is_video = False
    mock_post.owner_username = "testuser"
    mock_post.date_utc.strftime.return_value = "2026-04-19"
    mock_post.caption = "A beautiful shot #photography"

    with patch("ytk.instagram.instaloader") as mock_il:
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.return_value = mock_post
        result = fetch_instagram("https://www.instagram.com/p/ABC123/")

    mock_il.Post.from_shortcode.assert_called_once_with(
        mock_il.Instaloader.return_value.context,
        "ABC123",
    )
    assert isinstance(result, InstagramPost)
    assert result.username == "testuser"
    assert result.timestamp == "2026-04-19"
    assert result.images == ["https://cdn.instagram.com/image.jpg"]
    assert result.video_path is None
    assert result.caption == "A beautiful shot #photography"


def test_fetch_instagram_carousel():
    from ytk.instagram import fetch_instagram

    node1, node2 = MagicMock(), MagicMock()
    node1.display_url = "https://cdn.instagram.com/img1.jpg"
    node2.display_url = "https://cdn.instagram.com/img2.jpg"

    mock_post = MagicMock()
    mock_post.typename = "GraphSidecar"
    mock_post.is_video = False
    mock_post.get_sidecar_nodes.return_value = [node1, node2]
    mock_post.owner_username = "carousel_user"
    mock_post.date_utc.strftime.return_value = "2026-04-19"
    mock_post.caption = "A carousel post"

    with patch("ytk.instagram.instaloader") as mock_il:
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.return_value = mock_post
        result = fetch_instagram("https://www.instagram.com/p/CAROUSEL/")

    assert result.images == [
        "https://cdn.instagram.com/img1.jpg",
        "https://cdn.instagram.com/img2.jpg",
    ]


def test_fetch_instagram_reel_downloads_video(tmp_path):
    from ytk.instagram import fetch_instagram

    fake_video = tmp_path / "reel.mp4"
    fake_video.write_bytes(b"fakevideo")

    mock_post = MagicMock()
    mock_post.typename = "GraphVideo"
    mock_post.is_video = True
    mock_post.owner_username = "reeluser"
    mock_post.date_utc.strftime.return_value = "2026-04-19"
    mock_post.caption = "Check this out"

    with patch("ytk.instagram.instaloader") as mock_il, \
         patch("ytk.instagram._download_reel", return_value=fake_video):
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.return_value = mock_post
        result = fetch_instagram("https://www.instagram.com/reel/XYZ/")

    assert result.video_path == fake_video


def test_fetch_instagram_none_caption_becomes_empty_string():
    from ytk.instagram import fetch_instagram

    mock_post = MagicMock()
    mock_post.typename = "GraphImage"
    mock_post.url = "https://cdn.instagram.com/image.jpg"
    mock_post.is_video = False
    mock_post.owner_username = "silentuser"
    mock_post.date_utc.strftime.return_value = "2026-04-19"
    mock_post.caption = None

    with patch("ytk.instagram.instaloader") as mock_il:
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.return_value = mock_post
        result = fetch_instagram("https://www.instagram.com/p/NOCAPTION/")

    assert result.caption == ""


def test_fetch_instagram_instaloader_error_raises():
    from ytk.instagram import fetch_instagram

    with patch("ytk.instagram.instaloader") as mock_il:
        mock_il.Instaloader.return_value = MagicMock()
        mock_il.Post.from_shortcode.side_effect = Exception("Post not found")
        with pytest.raises(ValueError, match="Failed to fetch"):
            fetch_instagram("https://www.instagram.com/p/MISSING/")
