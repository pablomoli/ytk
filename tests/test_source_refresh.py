from datetime import datetime

import pytest

from ytk import reels
from ytk.imessage import MessageEntry, Session
from ytk.ui.source_refresh import (
    pull_imessage,
    pull_instagram,
    pull_pinterest,
    pull_tiktok,
    pull_youtube,
)


def test_youtube_deduplicates_pending_batch_and_processed_videos() -> None:
    state = reels.ReelsState(
        pending=[reels.ReelItem(url="https://www.youtube.com/watch?v=known", source="youtube")]
    )
    videos = [
        {"video_id": "new", "title": "New title", "added_at": "2026-07-04T01:00:00Z"},
        {"video_id": "new", "title": "Duplicate", "added_at": "2026-07-04T01:00:00Z"},
        {"video_id": "known", "title": "Known", "added_at": "2026-07-03T01:00:00Z"},
        {"video_id": "done", "title": "Done", "added_at": "2026-07-02T01:00:00Z"},
    ]

    inserted = pull_youtube(state, lambda: videos, lambda video_id: video_id == "done")

    assert inserted == 1
    assert [item.url for item in state.pending] == [
        "https://www.youtube.com/watch?v=known",
        "https://www.youtube.com/watch?v=new",
    ]
    assert state.pending[-1].title == "New title"
    assert state.pending[-1].author is None
    assert state.pending[-1].shared_at == "2026-07-04"


def test_pinterest_normalizes_feed_metadata_and_skips_known_urls() -> None:
    known = "https://www.pinterest.com/pin/known/"
    state = reels.ReelsState(pending=[reels.ReelItem(url=known, source="pinterest")])

    inserted = pull_pinterest(
        state,
        lambda: [
            {"url": known, "title": "Known", "image": None, "date": None},
            {
                "url": "https://www.pinterest.com/pin/new/",
                "title": "A pin",
                "image": "https://i.pinimg.com/new.jpg",
                "date": "2026-07-04",
            },
        ],
    )

    assert inserted == 1
    item = state.pending[-1]
    assert item.source == "pinterest"
    assert item.title == "A pin"
    assert item.author is None
    assert item.preview_url == "https://i.pinimg.com/new.jpg"
    assert item.shared_at == "2026-07-04"


def test_imessage_keeps_prose_with_its_session_and_routes_bare_links() -> None:
    start = datetime(2026, 4, 19, 19, 0)
    prose = Session(
        contact="+1555",
        start=start,
        end=start,
        messages=[
            MessageEntry("Me", "Apr 19, 2026 7:00:00 PM", "watch https://youtu.be/abc later")
        ],
    )
    links = Session(
        contact="+1555",
        start=start,
        end=start,
        messages=[MessageEntry("Me", "Apr 19, 2026 7:01:00 PM", "https://example.com/a")],
        override=True,
    )
    state = reels.ReelsState()
    auto_ingest_ids: list[str] = []

    inserted = pull_imessage(state, lambda: [prose, links], auto_ingest_ids)

    assert inserted == 2
    assert state.pending[0].url == prose.note_id
    assert state.pending[0].source == "imessage"
    assert state.pending[0].text == "watch https://youtu.be/abc later"
    assert state.pending[1].url == "https://example.com/a"
    assert state.pending[1].source == "web"
    assert auto_ingest_ids == ["https://example.com/a"]


def test_pull_youtube_stores_title_as_title() -> None:
    state = reels.ReelsState()
    videos = [
        {"video_id": "abc123DEF45", "title": "Video title", "added_at": "2026-08-01T00:00:00Z"}
    ]
    pull_youtube(state, lambda: videos, lambda vid: False)
    row = state.pending[0]
    assert row.title == "Video title"
    assert row.author is None
    assert row.preview_url == "https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg"


def test_pull_pinterest_stores_title_as_title() -> None:
    state = reels.ReelsState()
    pins = [
        {
            "url": "https://pin.example/1",
            "title": "Pin title",
            "image": "https://img/1.jpg",
            "date": "2026-08-01",
        }
    ]
    pull_pinterest(state, lambda: pins)
    row = state.pending[0]
    assert row.title == "Pin title"
    assert row.author is None


@pytest.mark.parametrize("adapter", [pull_instagram, pull_tiktok])
def test_state_pull_adapters_return_provider_counts(adapter) -> None:
    state = reels.ReelsState()

    assert adapter(state, lambda current: 3 if current is state else 0) == 3
