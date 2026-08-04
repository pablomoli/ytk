"""Provider-specific queue normalization for hub source refreshes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import NotRequired, Protocol, TypedDict, cast

from ytk import reels
from ytk.imessage import Session, split_urls


class YoutubeVideo(TypedDict):
    video_id: str
    title: NotRequired[str | None]
    added_at: NotRequired[str | None]


class PinterestPin(TypedDict):
    url: str
    title: NotRequired[str | None]
    image: NotRequired[str | None]
    date: NotRequired[str | None]


type StatePuller = Callable[[reels.ReelsState], int]
type YoutubeFetcher = Callable[[], Iterable[YoutubeVideo]]
type ProcessedVideoCheck = Callable[[str], bool]
type PinterestFetcher = Callable[[], Iterable[PinterestPin]]
type IMessageFetcher = Callable[[], Iterable[Session]]


class RefreshState(Protocol):
    pending: list[reels.ReelItem]
    imessage_seen: list[str]


def _state(state: reels.ReelsState) -> RefreshState:
    return cast("RefreshState", state)


def _pending(state: reels.ReelsState) -> list[reels.ReelItem]:
    return _state(state).pending


def pull_instagram(state: reels.ReelsState, puller: StatePuller) -> int:
    return puller(state)


def pull_tiktok(state: reels.ReelsState, puller: StatePuller) -> int:
    return puller(state)


def pull_reddit(state: reels.ReelsState, puller: StatePuller) -> int:
    return puller(state)


def pull_youtube(
    state: reels.ReelsState,
    fetch: YoutubeFetcher,
    is_processed: ProcessedVideoCheck,
) -> int:
    pending = _pending(state)
    known = {item.url for item in pending}
    inserted = 0
    for video in fetch():
        video_id = video["video_id"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        if url in known or is_processed(video_id):
            continue
        known.add(url)
        pending.append(
            reels.ReelItem(
                url=url,
                title=video.get("title") or None,
                shared_at=(video.get("added_at") or "")[:10] or None,
                preview_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                source="youtube",
            )
        )
        inserted += 1
    return inserted


def pull_pinterest(state: reels.ReelsState, fetch: PinterestFetcher) -> int:
    pending = _pending(state)
    known = {item.url for item in pending}
    inserted = 0
    for pin in fetch():
        url = pin["url"]
        if url in known:
            continue
        known.add(url)
        pending.append(
            reels.ReelItem(
                url=url,
                title=pin.get("title"),
                shared_at=pin.get("date"),
                preview_url=pin.get("image"),
                source="pinterest",
            )
        )
        inserted += 1
    return inserted


def pull_imessage(
    state: reels.ReelsState,
    fetch: IMessageFetcher,
    auto_ingest_ids: list[str],
) -> int:
    pending = _pending(state)
    refresh_state = _state(state)
    seen = set(refresh_state.imessage_seen)
    known = {item.url for item in pending}
    inserted = 0

    for session in fetch():
        if session.note_id in seen or session.note_id in known:
            continue
        refresh_state.imessage_seen.append(session.note_id)

        full = "\n\n".join(message.text for message in session.messages)
        urls, prose = split_urls(full)
        if prose:
            pending.append(
                reels.ReelItem(
                    url=session.note_id,
                    author=session.date,
                    shared_at=session.start.strftime("%Y-%m-%d"),
                    source="imessage",
                    text=full,
                )
            )
            inserted += 1
            if session.override:
                auto_ingest_ids.append(session.note_id)
            continue

        for url in urls:
            if url in known:
                continue
            known.add(url)
            pending.append(
                reels.ReelItem(
                    url=url,
                    shared_at=session.start.strftime("%Y-%m-%d"),
                    source=reels.classify_url(url),
                )
            )
            inserted += 1
            if session.override:
                auto_ingest_ids.append(url)

    return inserted
