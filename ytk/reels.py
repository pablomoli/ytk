"""Instagram DM self-thread link discovery via instagrapi (session-cookie auth).

Discovery only — ingestion goes through the existing `ytk add` pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

_LINK_RE = re.compile(r"https?://www\.instagram\.com/(reel|p)/([\w-]+)")

STATE_PATH = Path.home() / ".ytk" / "reels_state.json"
SETTINGS_PATH = Path.home() / ".ytk" / "instagram_session.json"


@dataclass
class ReelsState:
    thread_id: str | None = None
    last_seen_message_id: str | None = None


def get_client(sessionid: str, settings_path: Path = SETTINGS_PATH):
    """Logged-in instagrapi client, presenting a stable device across runs.

    A fresh random device UUID on every login is Instagram's main automation
    flag, so device settings are persisted and reloaded before each login.
    """
    if not sessionid:
        raise ValueError(
            "INSTAGRAM_SESSIONID is not set. Copy the 'sessionid' cookie from an "
            "instagram.com browser session into .env (or ~/.ytk/.env)."
        )
    from instagrapi import Client

    client = Client()
    if settings_path.exists():
        client.load_settings(settings_path)
    client.login_by_sessionid(sessionid)
    client.dump_settings(settings_path)
    return client


def load_state(path: Path = STATE_PATH) -> ReelsState:
    """Load the sync cursor. Missing file means first run: empty state."""
    if not path.exists():
        return ReelsState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ReelsState(
        thread_id=raw.get("thread_id"),
        last_seen_message_id=raw.get("last_seen_message_id"),
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


def fetch_new_links(client, state: ReelsState) -> tuple[list[str], ReelsState]:
    """Return (links oldest-first, advanced state) for messages newer than the cursor.

    The API returns messages newest-first; an empty cursor drains the whole thread.
    """
    thread = find_self_thread(client)
    messages = client.direct_messages(thread.id, amount=0)

    new = []
    for m in messages:
        if state.last_seen_message_id is not None and str(m.id) == str(state.last_seen_message_id):
            break
        new.append(m)

    links = extract_links(reversed(new))
    newest_id = str(messages[0].id) if messages else state.last_seen_message_id
    return links, ReelsState(thread_id=str(thread.id), last_seen_message_id=newest_id)
