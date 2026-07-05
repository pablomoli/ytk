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
class ReelItem:
    """A queued link plus whatever metadata its discovery source carried."""

    url: str
    author: str | None = None       # content author's username, not the sender
    shared_at: str | None = None    # YYYY-MM-DD the item entered the queue
    preview_url: str | None = None  # cover image (signed CDN URL, expires)
    source: str = "instagram"       # instagram | tiktok | youtube | web


def classify_url(url: str) -> str:
    """Classify a URL into an ingest source (mirrors the `add` CLI dispatch)."""
    if re.search(r"instagram\.com/", url):
        return "instagram"
    if re.search(r"tiktok\.com/", url):
        return "tiktok"
    if re.search(r"(?:youtube\.com/|youtu\.be/)", url):
        return "youtube"
    return "web"


def _as_item(entry) -> ReelItem:
    """Normalize a pending entry: legacy bare-URL strings become ReelItems."""
    if isinstance(entry, ReelItem):
        return entry
    if isinstance(entry, str):
        return ReelItem(url=entry, source=classify_url(entry))
    return ReelItem(
        url=entry["url"],
        author=entry.get("author"),
        shared_at=entry.get("shared_at"),
        preview_url=entry.get("preview_url"),
        source=entry.get("source") or classify_url(entry["url"]),
    )


def add_urls(state: "ReelsState", urls: list[str]) -> list[ReelItem]:
    """Append pasted URLs to the pending queue, classified and deduped.

    Returns the items actually added (dupes against the queue and within the
    input are dropped).
    """
    known = {_as_item(e).url for e in state.pending}
    added: list[ReelItem] = []
    for url in urls:
        url = url.strip()
        if not url or url in known:
            continue
        known.add(url)
        item = ReelItem(url=url, source=classify_url(url))
        added.append(item)
        state.pending.append(item)
    return added


@dataclass
class ReelsState:
    thread_id: str | None = None
    last_seen_message_id: str | None = None
    pending: list = field(default_factory=list)  # list[ReelItem]


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
        pending=[_as_item(e) for e in raw.get("pending", [])],
    )


def save_state(state: ReelsState, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def extract_items(messages) -> list[ReelItem]:
    """Extract reel/post items from DM messages, deduped by URL, order preserved.

    Handles shared reels (clip and current xma_clip), shared posts, and bare
    instagram.com links pasted as text. Metadata comes straight from the share
    payload — no extra API calls.
    """
    items: list[ReelItem] = []
    seen: set[str] = set()

    def add(url: str, message, author=None, preview=None) -> None:
        if url in seen:
            return
        seen.add(url)
        ts = getattr(message, "timestamp", None)
        items.append(
            ReelItem(
                url=url,
                author=author,
                shared_at=ts.strftime("%Y-%m-%d") if ts else None,
                preview_url=str(preview) if preview else None,
            )
        )

    for m in messages:
        if m.item_type == "clip" and getattr(m, "clip", None):
            clip = m.clip
            add(
                f"https://www.instagram.com/reel/{clip.code}/",
                m,
                author=getattr(getattr(clip, "user", None), "username", None),
                preview=getattr(clip, "thumbnail_url", None),
            )
        elif m.item_type == "media_share" and getattr(m, "media_share", None):
            share = m.media_share
            add(
                f"https://www.instagram.com/p/{share.code}/",
                m,
                author=getattr(getattr(share, "user", None), "username", None),
                preview=getattr(share, "thumbnail_url", None),
            )
        elif m.item_type.startswith("xma") and getattr(m, "xma_share", None):
            xma = m.xma_share
            for url_field in ("video_url", "target_url"):
                url = getattr(xma, url_field, None) or ""
                for kind, code in _LINK_RE.findall(str(url)):
                    add(
                        f"https://www.instagram.com/{kind}/{code}/",
                        m,
                        author=getattr(xma, "header_title_text", None),
                        preview=getattr(xma, "preview_url", None),
                    )
        elif m.item_type == "text" and getattr(m, "text", None):
            for kind, code in _LINK_RE.findall(m.text):
                add(f"https://www.instagram.com/{kind}/{code}/", m)
    return items


def extract_links(messages) -> list[str]:
    """Extract just the canonical URLs (see extract_items)."""
    return [item.url for item in extract_items(messages)]


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


def fetch_new_items(
    client, state: ReelsState, peer: str | None = None
) -> tuple[list[ReelItem], ReelsState]:
    """Return (items oldest-first, advanced state) for messages newer than the cursor.

    The capture thread is the one-on-one thread with `peer` when given (the
    two-account pattern), else the note-to-self thread. The API returns messages
    newest-first; an empty cursor drains the whole thread.
    """
    thread = find_peer_thread(client, peer) if peer else find_self_thread(client)
    messages = _messages_until_cursor(client, thread.id, state.last_seen_message_id)

    new = []
    for m in messages:
        if state.last_seen_message_id is not None and str(m.id) == str(state.last_seen_message_id):
            break
        new.append(m)

    items = extract_items(reversed(new))
    newest_id = str(messages[0].id) if messages else state.last_seen_message_id
    return items, ReelsState(
        thread_id=str(thread.id),
        last_seen_message_id=newest_id,
        pending=list(state.pending),
    )


def _messages_until_cursor(client, thread_id, cursor_id: str | None):
    """Fetch messages newest-first, but only as many pages as needed.

    With no cursor (first run) the whole thread is drained. With a cursor,
    request small batches and grow until the cursor message appears — a normal
    sync usually needs a single page instead of re-reading hundreds of messages.
    """
    if cursor_id is None:
        return client.direct_messages(thread_id, amount=0)

    amount = 20
    while True:
        messages = client.direct_messages(thread_id, amount=amount)
        if any(str(m.id) == str(cursor_id) for m in messages):
            return messages
        if len(messages) < amount:
            # cursor message was deleted or thread is shorter than requested;
            # everything fetched is everything there is
            return messages
        amount *= 2


def fetch_new_links(
    client, state: ReelsState, peer: str | None = None
) -> tuple[list[str], ReelsState]:
    """URL-only variant of fetch_new_items."""
    items, new_state = fetch_new_items(client, state, peer=peer)
    return [i.url for i in items], new_state


def refresh(client, state: ReelsState, peer: str | None = None) -> ReelsState:
    """Drain new DM messages into the pending queue and advance the cursor.

    Advancing the cursor here is safe because the items are persisted in
    `pending` until each one is ingested. Existing pending entries win over
    rediscovered duplicates so metadata is never clobbered.
    """
    items, new_state = fetch_new_items(client, state, peer=peer)
    existing = [_as_item(e) for e in state.pending]
    known = {i.url for i in existing}
    new_state.pending = [*existing, *[i for i in items if i.url not in known]]
    return new_state


GALLERY_PATH = Path.home() / ".ytk" / "reels_gallery.html"


def gallery_html(items: list[ReelItem]) -> str:
    """Render pending items as a click-to-select cover grid, newest first.

    Card numbers match the terminal picker's numbering (position in the pending
    list). Clicking a card toggles selection; a sticky bar builds the compact
    selection string (e.g. 1,5,12-14) to paste back into `ytk reels`.
    """
    import html as _html

    numbered = list(enumerate(items, 1))
    numbered.sort(key=lambda pair: (pair[1].shared_at or "", pair[0]), reverse=True)

    cards = []
    for i, item in numbered:
        url = _html.escape(item.url, quote=True)
        author = _html.escape(item.author) if item.author else "unknown"
        date = _html.escape(item.shared_at) if item.shared_at else ""
        if item.preview_url:
            cover = f'<img src="{_html.escape(item.preview_url, quote=True)}" loading="lazy">'
        else:
            cover = '<div class="noimg">no cover</div>'
        cards.append(
            f'<div class="card" data-index="{i}">'
            f'<span class="n">{i}</span>{cover}'
            f'<span class="meta">@{author} · {date} '
            f'<a class="open" href="{url}" target="_blank">open</a></span></div>'
        )

    style = (
        "body{font-family:system-ui;background:#111;color:#eee;margin:1rem;"
        "padding-bottom:4.5rem}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.75rem}"
        ".card{position:relative;background:#1c1c1c;border-radius:8px;overflow:hidden;"
        "cursor:pointer;outline:3px solid transparent}"
        ".card.sel{outline-color:#4ade80}"
        ".card.sel .n{background:#4ade80;color:#000}"
        ".card img{width:100%;aspect-ratio:9/16;object-fit:cover;display:block}"
        ".noimg{width:100%;aspect-ratio:9/16;display:flex;align-items:center;"
        "justify-content:center;color:#777}"
        ".n{position:absolute;top:.4rem;left:.4rem;background:#000c;padding:.1rem .5rem;"
        "border-radius:999px;font-weight:700}"
        ".meta{display:block;padding:.4rem .5rem;font-size:.8rem;color:#bbb}"
        ".meta a{color:#7dd3fc;text-decoration:none}"
        "#selbar{position:fixed;left:0;right:0;bottom:0;background:#000e;"
        "display:flex;gap:.75rem;align-items:center;padding:.6rem 1rem;font-size:.9rem}"
        "#selstr{flex:1;background:#1c1c1c;color:#eee;border:1px solid #333;"
        "border-radius:6px;padding:.4rem .6rem;font-family:ui-monospace,monospace}"
        "#copy{background:#4ade80;color:#000;border:0;border-radius:6px;"
        "padding:.45rem .9rem;font-weight:700;cursor:pointer}"
    )
    script = """
const sel = new Set();
function compact(nums) {
  nums = [...nums].sort((a, b) => a - b);
  const parts = [];
  for (let i = 0; i < nums.length;) {
    let j = i;
    while (j + 1 < nums.length && nums[j + 1] === nums[j] + 1) j++;
    parts.push(j > i ? nums[i] + "-" + nums[j] : String(nums[i]));
    i = j + 1;
  }
  return parts.join(",");
}
function render() {
  document.getElementById("selcount").textContent = sel.size + " selected";
  document.getElementById("selstr").value = sel.size ? compact(sel) : "none";
}
document.querySelectorAll(".card").forEach(card => {
  card.addEventListener("click", e => {
    if (e.target.closest("a")) return;
    const i = Number(card.dataset.index);
    if (sel.has(i)) { sel.delete(i); } else { sel.add(i); }
    card.classList.toggle("sel");
    render();
  });
});
document.getElementById("copy").addEventListener("click", () => {
  const box = document.getElementById("selstr");
  box.select();
  if (navigator.clipboard) navigator.clipboard.writeText(box.value);
  else document.execCommand("copy");
});
render();
"""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>ytk reels — {len(items)} pending</title><style>{style}</style></head>"
        f"<body><main>{''.join(cards)}</main>"
        '<div id="selbar"><span id="selcount">0 selected</span>'
        '<input id="selstr" readonly value="none">'
        '<button id="copy">copy</button>'
        "<span>paste into: Ingest which?</span></div>"
        f"<script>{script}</script></body></html>"
    )


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
