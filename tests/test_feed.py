"""Tests for the _collect_feed_urls helper in ytk.cli."""

from ytk.cli import _collect_feed_urls


def test_collect_merges_args_and_file_dedupes(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text(
        "# my reels\n"
        "https://www.tiktok.com/@x/video/1\n"
        "\n"
        "https://www.tiktok.com/@x/video/2\n"
        "https://www.tiktok.com/@x/video/1\n",  # duplicate
        encoding="utf-8",
    )
    urls = _collect_feed_urls(str(f), ("https://www.tiktok.com/@x/video/2",))
    assert urls == [
        "https://www.tiktok.com/@x/video/2",
        "https://www.tiktok.com/@x/video/1",
    ]


def test_collect_empty():
    assert _collect_feed_urls(None, ()) == []


def test_collect_file_only(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("https://www.tiktok.com/@x/video/9\n", encoding="utf-8")
    assert _collect_feed_urls(str(f), ()) == ["https://www.tiktok.com/@x/video/9"]
