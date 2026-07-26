"""Playlist discovery must actually call the YouTube API.

`_find_playlist_id` once read:

    response = service.playlists()  # type: ignore[...].list(**kwargs).execute()

The type-suppression comment was inserted mid-expression, so `.list().execute()`
sat inside the comment and the line evaluated to a bare Resource. Every YouTube
pull then died on `'Resource' object has no attribute 'get'`, and because
refresh_sources files per-source exceptions into `errors` rather than raising,
the hub reported success while the playlist never reached the queue.

These fakes only respond to the full list().execute() chain, so a truncated call
chain fails here instead of in production.
"""

import pytest

from ytk.scheduler import _find_playlist_id, fetch_playlist_videos


class FakeRequest:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def execute(self) -> dict:
        return self._payload


class FakeEndpoint:
    """Returns pages in order, one per list() call, and records the kwargs."""

    def __init__(self, pages: list[dict]) -> None:
        self._pages = pages
        self.calls: list[dict] = []

    def list(self, **kwargs) -> FakeRequest:
        self.calls.append(kwargs)
        return FakeRequest(self._pages[len(self.calls) - 1])


class FakeService:
    def __init__(self, playlist_pages: list[dict], item_pages: list[dict] | None = None) -> None:
        self._playlists = FakeEndpoint(playlist_pages)
        self._items = FakeEndpoint(item_pages or [{"items": []}])

    def playlists(self) -> FakeEndpoint:
        return self._playlists

    # camelCase mirrors the Google client's own method name, which is what the
    # code under test calls.
    def playlistItems(self) -> FakeEndpoint:
        return self._items


def test_finds_a_playlist_by_name() -> None:
    service = FakeService([{"items": [{"id": "PL123", "snippet": {"title": "ytk"}}]}])
    assert _find_playlist_id(service, "ytk") == "PL123"


def test_matches_the_name_case_insensitively() -> None:
    service = FakeService([{"items": [{"id": "PL1", "snippet": {"title": "YTK"}}]}])
    assert _find_playlist_id(service, "ytk") == "PL1"


def test_pages_through_playlists_until_it_finds_the_name() -> None:
    service = FakeService(
        [
            {"items": [{"id": "PLa", "snippet": {"title": "other"}}], "nextPageToken": "p2"},
            {"items": [{"id": "PLb", "snippet": {"title": "ytk"}}]},
        ]
    )
    assert _find_playlist_id(service, "ytk") == "PLb"
    assert service.playlists().calls[1]["pageToken"] == "p2"


def test_raises_when_no_playlist_matches() -> None:
    service = FakeService([{"items": [{"id": "PLa", "snippet": {"title": "other"}}]}])
    with pytest.raises(RuntimeError, match="No YouTube playlist named 'ytk'"):
        _find_playlist_id(service, "ytk")


def test_returns_the_playlist_videos() -> None:
    service = FakeService(
        [{"items": [{"id": "PL123", "snippet": {"title": "ytk"}}]}],
        [
            {
                "items": [
                    {
                        "snippet": {
                            "title": "A video",
                            "publishedAt": "2026-07-20T00:00:00Z",
                            "resourceId": {"videoId": "abc123"},
                        }
                    }
                ]
            }
        ],
    )

    videos = fetch_playlist_videos(service, "ytk")

    assert videos == [
        {"video_id": "abc123", "title": "A video", "added_at": "2026-07-20T00:00:00Z"}
    ]


def test_skips_items_with_no_video_id() -> None:
    """A deleted or private entry keeps its row but loses its resourceId."""
    service = FakeService(
        [{"items": [{"id": "PL123", "snippet": {"title": "ytk"}}]}],
        [{"items": [{"snippet": {"title": "gone", "resourceId": {}}}]}],
    )
    assert fetch_playlist_videos(service, "ytk") == []
