"""Instagram DM self-thread link discovery via instagrapi (session-cookie auth).

Discovery only — ingestion goes through the existing `ytk add` pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

_LINK_RE = re.compile(r"https?://www\.instagram\.com/(reel|p)/([\w-]+)")

STATE_PATH = Path.home() / ".ytk" / "reels_state.json"
SETTINGS_PATH = Path.home() / ".ytk" / "instagram_session.json"


@dataclass
class ReelsState:
    thread_id: str | None = None
    last_seen_message_id: str | None = None
    pending: list[str] = field(default_factory=list)


_client_cache: dict[tuple[str, str], object] = {}


def get_client(sessionid: str, settings_path: Path = SETTINGS_PATH):
    """Logged-in instagrapi client, presenting a stable device across runs.

    A fresh random device UUID on every login is Instagram's main automation
    flag, so device settings are persisted and reloaded before each login.
    The client is cached per process so a batch drain logs in exactly once.
    """
    if not sessionid:
        raise ValueError(
            "INSTAGRAM_SESSIONID is not set. Copy the 'sessionid' cookie from an "
            "instagram.com browser session into .env (or ~/.ytk/.env)."
        )
    cache_key = (sessionid, str(settings_path))
    if cache_key in _client_cache:
        return _client_cache[cache_key]

    from instagrapi import Client

    client = Client()
    if settings_path.exists():
        client.load_settings(settings_path)
    client.login_by_sessionid(sessionid)
    client.dump_settings(settings_path)
    _client_cache[cache_key] = client
    return client


def load_state(path: Path = STATE_PATH) -> ReelsState:
    """Load the sync cursor. Missing file means first run: empty state."""
    if not path.exists():
        return ReelsState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ReelsState(
        thread_id=raw.get("thread_id"),
        last_seen_message_id=raw.get("last_seen_message_id"),
        pending=raw.get("pending", []),
    )


def save_state(state: ReelsState, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def extract_links(messages) -> list[str]:
    """Extract reel/post URLs from DM messages, deduped, message order preserved.

    Handles shared reels (clip), shared posts (media_share), and bare
    instagram.com links pasted as text.
    """
    links: list[str] = []
    for m in messages:
        if m.item_type == "clip" and getattr(m, "clip", None):
            links.append(f"https://www.instagram.com/reel/{m.clip.code}/")
        elif m.item_type == "media_share" and getattr(m, "media_share", None):
            links.append(f"https://www.instagram.com/p/{m.media_share.code}/")
        elif m.item_type.startswith("xma") and getattr(m, "xma_share", None):
            for field in ("video_url", "target_url"):
                url = getattr(m.xma_share, field, None) or ""
                links.extend(
                    f"https://www.instagram.com/{kind}/{code}/"
                    for kind, code in _LINK_RE.findall(url)
                )
        elif m.item_type == "text" and getattr(m, "text", None):
            links.extend(
                f"https://www.instagram.com/{kind}/{code}/"
                for kind, code in _LINK_RE.findall(m.text)
            )
    return list(dict.fromkeys(links))


def find_self_thread(client):
    """Return the note-to-self DM thread: the one whose only participant is you."""
    me = str(client.user_id)
    for thread in client.direct_threads(amount=0):
        pks = [str(u.pk) for u in thread.users]
        if pks in ([], [me]):
            return thread
    raise ValueError(
        "No note-to-self thread found (a DM thread whose only participant is you)."
    )


def find_peer_thread(client, peer: str):
    """Return the one-on-one DM thread with the given username (e.g. a second account)."""
    want = peer.lower()
    for thread in client.direct_threads(amount=0):
        if len(thread.users) == 1 and thread.users[0].username.lower() == want:
            return thread
    raise ValueError(f"No one-on-one thread found with @{peer}.")


def fetch_new_links(
    client, state: ReelsState, peer: str | None = None
) -> tuple[list[str], ReelsState]:
    """Return (links oldest-first, advanced state) for messages newer than the cursor.

    The capture thread is the one-on-one thread with `peer` when given (the
    two-account pattern), else the note-to-self thread. The API returns messages
    newest-first; an empty cursor drains the whole thread.
    """
    thread = find_peer_thread(client, peer) if peer else find_self_thread(client)
    messages = client.direct_messages(thread.id, amount=0)

    new = []
    for m in messages:
        if state.last_seen_message_id is not None and str(m.id) == str(state.last_seen_message_id):
            break
        new.append(m)

    links = extract_links(reversed(new))
    newest_id = str(messages[0].id) if messages else state.last_seen_message_id
    return links, ReelsState(
        thread_id=str(thread.id),
        last_seen_message_id=newest_id,
        pending=list(state.pending),
    )


def refresh(client, state: ReelsState, peer: str | None = None) -> ReelsState:
    """Drain new DM messages into the pending queue and advance the cursor.

    Advancing the cursor here is safe because the links are persisted in
    `pending` until each one is ingested.
    """
    links, new_state = fetch_new_links(client, state, peer=peer)
    new_state.pending = list(dict.fromkeys([*state.pending, *links]))
    return new_state


def parse_selection(raw: str, count: int) -> list[int]:
    """Parse a picker selection ('all', 'none', '1,3,5-9') into 0-based indices."""
    text = raw.strip().lower()
    if text in ("", "none"):
        return []
    if text == "all":
        return list(range(count))

    indices: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise ValueError(f"Cannot parse selection part: {part!r}")
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if lo < 1 or hi > count or lo > hi:
            raise ValueError(f"Selection {part!r} out of range 1-{count}.")
        indices.update(range(lo - 1, hi))
    return sorted(indices)
