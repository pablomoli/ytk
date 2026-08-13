"""Tests for the feed URL helpers in ytk.cli."""

import pytest

from ytk.cli import _collect_feed_urls, _split_overnight

YT = "https://www.youtube.com/watch?v=abc123"
TT = "https://www.tiktok.com/@x/video/1"
IG = "https://www.instagram.com/reel/DXYZ/"
WEB = "https://example.com/an-article"


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


def test_split_routes_only_sources_the_batch_can_actually_ingest():
    overnight, immediate = _split_overnight([YT, TT, IG, WEB], enabled=True)
    assert overnight == [YT]
    assert immediate == [TT, IG, WEB]


def test_split_preserves_every_url_across_the_partition():
    urls = [YT, TT, IG, WEB, YT.replace("abc123", "def456")]
    overnight, immediate = _split_overnight(urls, enabled=True)
    assert sorted(overnight + immediate) == sorted(urls)


def test_split_disabled_sends_everything_to_the_synchronous_path():
    assert _split_overnight([YT, TT], enabled=False) == ([], [YT, TT])


@pytest.mark.parametrize("url", [TT, IG, WEB])
def test_sources_the_batch_would_drop_are_never_routed_overnight(url):
    """The batch fetcher raises FilteredOut — terminal, never retried — for any
    source without an adapter. Routing one overnight would drop it silently
    instead of ingesting it, so the partition must keep it synchronous."""
    from ytk import batch, batch_cli
    from ytk.batch_adapters import OVERNIGHT_SOURCES
    from ytk.reels import classify_url

    assert classify_url(url) not in OVERNIGHT_SOURCES

    item = batch.BatchItem(url=url, source=classify_url(url))
    with pytest.raises(batch.FilteredOut):
        batch_cli._fetch(item)

    overnight, immediate = _split_overnight([url], enabled=True)
    assert overnight == []
    assert immediate == [url]
