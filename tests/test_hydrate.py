from ytk import hydrate, reels


def test_youtube_video_id_variants():
    assert hydrate.youtube_video_id("https://www.youtube.com/watch?v=abc123DEF45") == "abc123DEF45"
    assert hydrate.youtube_video_id("https://youtu.be/abc123DEF45") == "abc123DEF45"
    assert hydrate.youtube_video_id("https://www.youtube.com/shorts/abc123DEF45") == "abc123DEF45"
    assert hydrate.youtube_video_id("https://example.com/page") is None


def test_hydrate_youtube_fills_from_oembed():
    item = reels.ReelItem(url="https://www.youtube.com/watch?v=abc123DEF45", source="youtube")
    changed = hydrate.hydrate_item(
        item,
        fetch_json=lambda url: {
            "title": "Video title",
            "author_name": "Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg",
        },
        fetch_html=lambda url: "",
    )
    assert item.title == "Video title"
    assert item.author == "Channel"
    assert item.preview_url == "https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg"
    assert item.hydrated_at is not None
    assert item.hydrate_error is None
    assert changed is True


def test_hydrate_youtube_offline_fallback_derives_thumb():
    item = reels.ReelItem(url="https://youtu.be/abc123DEF45", source="youtube")

    def boom(url):
        raise OSError("no network")

    hydrate.hydrate_item(item, fetch_json=boom, fetch_html=boom)
    assert item.preview_url == "https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg"
    assert item.hydrate_error is not None
    assert item.hydrated_at is not None


def test_hydrate_web_parses_og_then_title_tag():
    html = (
        "<html><head>"
        '<meta property="og:title" content="OG Title">'
        '<meta property="og:image" content="https://example.com/og.jpg">'
        '<meta property="og:description" content="Desc">'
        "<title>Tag title</title></head><body></body></html>"
    )
    item = reels.ReelItem(url="https://example.com/post", source="web")
    hydrate.hydrate_item(item, fetch_json=lambda u: {}, fetch_html=lambda u: html)
    assert item.title == "OG Title"
    assert item.preview_url == "https://example.com/og.jpg"
    assert item.text == "Desc"


def test_hydrate_web_falls_back_to_title_tag():
    html = "<html><head><title>Only title</title></head><body></body></html>"
    item = reels.ReelItem(url="https://example.com/post", source="web")
    hydrate.hydrate_item(item, fetch_json=lambda u: {}, fetch_html=lambda u: html)
    assert item.title == "Only title"


def test_hydrate_fills_only_empty_except_preview():
    item = reels.ReelItem(
        url="https://www.youtube.com/watch?v=abc123DEF45",
        source="youtube",
        title="Kept",
        author="r/sub",
        preview_url="https://b.thumbs.redditmedia.com/tiny.jpg",
    )
    hydrate.hydrate_item(
        item,
        fetch_json=lambda url: {
            "title": "New",
            "author_name": "Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg",
        },
        fetch_html=lambda url: "",
    )
    assert item.title == "Kept"
    assert item.author == "r/sub"
    assert item.preview_url == "https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg"


def test_hydrate_failure_marks_and_does_not_raise():
    item = reels.ReelItem(url="https://example.com/post", source="web")

    def boom(url):
        raise OSError("dns")

    hydrate.hydrate_item(item, fetch_json=boom, fetch_html=boom)
    assert item.hydrated_at is not None
    assert "OSError" in item.hydrate_error


def test_hydrate_instagram_skips_fetch_without_stamping():
    item = reels.ReelItem(url="https://www.instagram.com/reel/abc123/", source="instagram")

    def boom(url):
        raise AssertionError("fetcher must not be called for instagram")

    changed = hydrate.hydrate_item(item, fetch_json=boom, fetch_html=boom)
    assert item.hydrated_at is None
    assert item.hydrate_error is None
    assert item.title is None
    assert item.author is None
    assert item.text is None
    assert item.preview_url is None
    assert changed is False


def test_hydrate_tiktok_skips_fetch_without_stamping():
    item = reels.ReelItem(url="https://www.tiktok.com/@user/video/123", source="tiktok")

    def boom(url):
        raise AssertionError("fetcher must not be called for tiktok")

    changed = hydrate.hydrate_item(item, fetch_json=boom, fetch_html=boom)
    assert item.hydrated_at is None
    assert item.hydrate_error is None
    assert item.title is None
    assert item.author is None
    assert item.text is None
    assert item.preview_url is None
    assert changed is False


def test_hydrate_instagram_does_not_clobber_existing_preview():
    item = reels.ReelItem(
        url="https://www.instagram.com/p/xyz/",
        source="instagram",
        title="Kept",
        preview_url="https://scontent.cdninstagram.com/signed.jpg",
        hydrated_at="2026-08-01",
        hydrate_error="previous failure",
    )

    def boom(url):
        raise AssertionError("fetcher must not be called for instagram")

    changed = hydrate.hydrate_item(item, fetch_json=boom, fetch_html=boom)
    assert item.title == "Kept"
    assert item.preview_url == "https://scontent.cdninstagram.com/signed.jpg"
    assert item.hydrated_at == "2026-08-01"
    assert item.hydrate_error == "previous failure"
    assert changed is False
