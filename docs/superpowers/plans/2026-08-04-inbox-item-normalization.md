# Inbox Item Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give queue items real title/creator/body semantics, hydrate missing metadata via oEmbed/Open Graph, keep Reddit posts native (with cross-linked video ingestion), and fix the inbox card redundancy.

**Architecture:** Approach A from the spec — evolve the flat `ReelItem` dataclass in place behind its `_as_item` choke point; add a small `ytk/hydrate.py` module with injectable fetchers; adapters write canonical fields; the card renders `title || excerpt(text) || neutral`. Spec: `docs/superpowers/specs/2026-08-04-inbox-item-normalization-design.md`.

**Tech Stack:** Python stdlib (urllib, html.parser, dataclasses), pytest; React/TypeScript frontend tested with `vp exec vitest run`.

## Global Constraints

- Old `reels_state.json` files must load unchanged (`_as_item` defaults; no migration script).
- Hydration fills only empty fields, except `preview_url`, which it may upgrade.
- Reddit selftext capped at 2000 chars in the queue (#132 lesson).
- No code comments beyond 1-2 constraint lines; narrative goes in commit messages.
- Python tests: `uv run pytest -q tests/<file>`; frontend: `vp exec vitest run <file>` from `web/`.
- Nothing touches `ytk/store.py`; the retrieval eval gate is not in play.
- No emojis anywhere.

---

### Task 1: Schema — new `ReelItem` fields

**Files:**
- Modify: `ytk/reels.py:24-62` (`ReelItem`, `_as_item`)
- Test: `tests/test_reels.py`

**Interfaces:**
- Produces: `ReelItem` fields `title: str | None`, `attachments: list | None` (dicts `{url, kind}`), `hydrated_at: str | None`, `hydrate_error: str | None`. All later tasks rely on these exact names.

- [ ] **Step 1: Write the failing tests**

```python
def test_as_item_parses_new_fields():
    item = reels._as_item(
        {
            "url": "https://example.com/a",
            "title": "A title",
            "attachments": [{"url": "https://example.com/i.jpg", "kind": "image"}],
            "hydrated_at": "2026-08-04",
            "hydrate_error": None,
        }
    )
    assert item.title == "A title"
    assert item.attachments == [{"url": "https://example.com/i.jpg", "kind": "image"}]
    assert item.hydrated_at == "2026-08-04"
    assert item.hydrate_error is None


def test_as_item_defaults_new_fields_for_legacy_rows():
    item = reels._as_item({"url": "https://example.com/a"})
    assert item.title is None
    assert item.attachments is None
    assert item.hydrated_at is None
    assert item.hydrate_error is None


def test_state_roundtrip_preserves_new_fields(tmp_path):
    state = reels.ReelsState()
    state.pending.append(reels.ReelItem(url="https://example.com/a", title="T"))
    path = tmp_path / "state.json"
    reels.save_state(state, path)
    loaded = reels.load_state(path)
    assert loaded.pending[0].title == "T"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_reels.py -k "new_fields or roundtrip"`
Expected: FAIL — `TypeError: unexpected keyword argument 'title'`

- [ ] **Step 3: Implement**

In the `ReelItem` dataclass add after `text`:

```python
    title: str | None = None  # content title; never a handle or URL
    attachments: list | None = None  # [{url, kind: image|video|link}]
    hydrated_at: str | None = None  # stamped on any hydration attempt
    hydrate_error: str | None = None  # set on permanent failure
```

In `_as_item`, extend the dict branch:

```python
        title=entry.get("title"),
        attachments=entry.get("attachments"),
        hydrated_at=entry.get("hydrated_at"),
        hydrate_error=entry.get("hydrate_error"),
```

Tighten the existing field comments: `author` — "creator provenance (channel, username, r/sub); never the content title", `text` — "body/caption text; never a title", `preview_url` — "ephemeral; hydration and rediscovery may overwrite".

- [ ] **Step 4: Run full reels suite**

Run: `uv run pytest -q tests/test_reels.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ytk/reels.py tests/test_reels.py
git commit -m "feat(inbox): ReelItem gains title, attachments, hydration stamps (#163)"
```

---

### Task 2: Hydrator module

**Files:**
- Create: `ytk/hydrate.py`
- Test: `tests/test_hydrate.py`

**Interfaces:**
- Consumes: `reels.ReelItem`, `reels.classify_url`.
- Produces:
  - `youtube_video_id(url: str) -> str | None`
  - `hydrate_item(item: ReelItem, *, fetch_json, fetch_html) -> bool` — mutates the item, stamps `hydrated_at` (ISO date) on every attempt, sets `hydrate_error` on failure, returns True when `preview_url` changed (callers use this for cover invalidation). `fetch_json(url) -> dict` and `fetch_html(url) -> str` are injectable; module provides `default_fetch_json` / `default_fetch_html` (browser User-Agent, 15s timeout, 512KB read cap).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_hydrate.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ytk.hydrate'`

- [ ] **Step 3: Implement `ytk/hydrate.py`**

```python
"""Fill a queue item's missing metadata from its URL.

oEmbed for YouTube, Open Graph tags for the general web. Fetchers are
injectable so tests never touch the network.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date
from html.parser import HTMLParser

from ytk import reels

_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/)|youtu\.be/)([\w-]{11})"
)
_UA = {"User-Agent": "Mozilla/5.0"}
_READ_CAP = 512 * 1024


def youtube_video_id(url: str) -> str | None:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def default_fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read(_READ_CAP).decode("utf-8", "replace"))


def default_fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(_READ_CAP).decode("utf-8", "replace")


class _HeadParser(HTMLParser):
    """og:/twitter: meta tags plus <title>, first value wins."""

    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag != "meta":
            return
        a = dict(attrs)
        key = a.get("property") or a.get("name") or ""
        content = a.get("content") or ""
        if key and content and key not in self.meta:
            self.meta[key] = content

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


def _web_fields(html: str) -> dict:
    p = _HeadParser()
    p.feed(html)
    m = p.meta
    return {
        "title": m.get("og:title") or m.get("twitter:title") or p.title or None,
        "preview_url": m.get("og:image") or m.get("twitter:image") or None,
        "text": m.get("og:description") or m.get("twitter:description") or None,
    }


def _youtube_fields(url: str, fetch_json) -> dict:
    oembed = (
        "https://www.youtube.com/oembed?"
        + urllib.parse.urlencode({"url": url, "format": "json"})
    )
    data = fetch_json(oembed)
    return {
        "title": data.get("title") or None,
        "author": data.get("author_name") or None,
        "preview_url": data.get("thumbnail_url") or None,
    }


def hydrate_item(item: reels.ReelItem, *, fetch_json=default_fetch_json, fetch_html=default_fetch_html) -> bool:
    """Mutate item in place; return True when preview_url changed."""
    old_preview = item.preview_url
    item.hydrated_at = date.today().isoformat()
    item.hydrate_error = None
    fields: dict = {}
    try:
        if reels.classify_url(item.url) == "youtube":
            fields = _youtube_fields(item.url, fetch_json)
        elif item.url.startswith("http"):
            fields = _web_fields(fetch_html(item.url))
    except Exception as exc:
        item.hydrate_error = f"{type(exc).__name__}: {exc}"

    vid = youtube_video_id(item.url)
    if vid and not fields.get("preview_url"):
        fields["preview_url"] = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

    for name in ("title", "author", "text"):
        if fields.get(name) and not getattr(item, name):
            setattr(item, name, fields[name])
    if fields.get("preview_url"):
        item.preview_url = fields["preview_url"]
    return item.preview_url != old_preview
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_hydrate.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ytk/hydrate.py tests/test_hydrate.py
git commit -m "feat(inbox): hydrator — oEmbed for YouTube, Open Graph for web (#163)"
```

---

### Task 3: Hydrate at enqueue (paste box)

**Files:**
- Modify: `ytk/ui/hub.py:150-157` (`queue_add`)
- Test: `tests/test_hub_queue.py` (create if absent; check for an existing hub test file first and extend it instead)

**Interfaces:**
- Consumes: `reels.add_urls`, `hydrate.hydrate_item`.
- Produces: `queue_add(urls: list[str]) -> int` unchanged signature; pasted items are hydrated before the state is saved.

- [ ] **Step 1: Write the failing test**

```python
def test_queue_add_hydrates_new_items(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "STATE_PATH", tmp_path / "state.json")

    def fake_hydrate(item, **kwargs):
        item.title = "Hydrated"
        item.hydrated_at = "2026-08-04"
        return False

    monkeypatch.setattr(hub.hydrate, "hydrate_item", fake_hydrate)
    added = hub.queue_add(["https://www.youtube.com/watch?v=abc123DEF45"])
    assert added == 1
    items = hub.queue_items()
    assert items[0].title == "Hydrated"
```

Match the existing hub test file's fixtures for `STATE_PATH`/locking; if none exists, this test defines the pattern.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_hub_queue.py -k hydrates`
Expected: FAIL — title is None

- [ ] **Step 3: Implement**

In `queue_add`, after `reels.add_urls(state, urls)` returns `added` and before `save_state`:

```python
    for item in added:
        hydrate.hydrate_item(item)
```

Import `hydrate` at the top of `hub.py` (`from ytk import hydrate`). Keep the network call inside the existing lock only if `queue_add` already holds it around the save; otherwise hydrate before acquiring the lock to avoid holding it during network I/O — mirror whichever structure `queue_add` currently has, hydrating the returned items before the state write.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_hub_queue.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ytk/ui/hub.py tests/test_hub_queue.py
git commit -m "feat(inbox): hydrate pasted URLs at enqueue (#163)"
```

---

### Task 4: Backfill pass in the refresh cycle

**Files:**
- Modify: `ytk/ui/hub.py` (refresh orchestrator around `hub.py:800-840`, where `state.last_pull_at` is stamped)
- Test: `tests/test_hub_queue.py`

**Interfaces:**
- Consumes: `hydrate.hydrate_item`, `ReelsState.last_pulls`.
- Produces: `hydrate_pending(state: ReelsState, limit: int = 25) -> int` in `hub.py` — walks `state.pending` newest-first (reversed list order), hydrates items with `hydrated_at is None`, stops at `limit`, returns count attempted. Wired into the refresh cycle behind a `last_pulls["hydrate"]` throttle (same cadence the source pulls use).

- [ ] **Step 1: Write the failing tests**

```python
def test_hydrate_pending_newest_first_and_limited(monkeypatch):
    state = reels.ReelsState()
    for i in range(5):
        state.pending.append(reels.ReelItem(url=f"https://example.com/{i}", source="web"))
    seen = []

    def fake_hydrate(item, **kwargs):
        seen.append(item.url)
        item.hydrated_at = "2026-08-04"
        return False

    monkeypatch.setattr(hub.hydrate, "hydrate_item", fake_hydrate)
    n = hub.hydrate_pending(state, limit=3)
    assert n == 3
    assert seen == [
        "https://example.com/4",
        "https://example.com/3",
        "https://example.com/2",
    ]


def test_hydrate_pending_skips_already_stamped(monkeypatch):
    state = reels.ReelsState()
    state.pending.append(
        reels.ReelItem(url="https://example.com/a", source="web", hydrated_at="2026-08-01")
    )
    monkeypatch.setattr(
        hub.hydrate, "hydrate_item", lambda item, **k: (_ for _ in ()).throw(AssertionError)
    )
    assert hub.hydrate_pending(state, limit=10) == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_hub_queue.py -k hydrate_pending`
Expected: FAIL — `hydrate_pending` not defined

- [ ] **Step 3: Implement**

```python
def hydrate_pending(state: reels.ReelsState, limit: int = 25) -> int:
    """Backfill metadata newest-first; every attempt stamps the item."""
    attempted = 0
    for item in reversed(state.pending):
        if attempted >= limit:
            break
        if item.hydrated_at is not None:
            continue
        changed = hydrate.hydrate_item(item)
        if changed:
            cover_invalidate(item.url)
        attempted += 1
    return attempted
```

`cover_invalidate` arrives in Task 8; until then call nothing on `changed` (leave the variable out) and wire the invalidation in Task 8's steps. In the refresh orchestrator, alongside the per-source pulls, add a `hydrate` entry throttled via `state.last_pulls["hydrate"] = now` after calling `hydrate_pending(state)` — same pattern as the neighboring source pulls, saved by the existing `save_state` call.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_hub_queue.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ytk/ui/hub.py tests/test_hub_queue.py
git commit -m "feat(inbox): newest-first hydration backfill in the refresh cycle (#163)"
```

---

### Task 5: Reddit stays Reddit

**Files:**
- Modify: `ytk/reddit_feed.py:143-176` (`is_external`, `post_to_reelitem`)
- Test: `tests/test_reddit_feed.py`

**Interfaces:**
- Consumes: `ReelItem` new fields from Task 1.
- Produces: `post_to_reelitem(post: dict) -> ReelItem` — always `source="reddit"`, `url` = permalink, `title` = post title, `text` = selftext capped at 2000 chars, `author` = `r/{subreddit}`, `attachments` carrying the external link (`kind="link"`) and the thumbnail is left in `preview_url` as before (hydration upgrades it). `is_external(post)` remains exported for the attachment decision but no longer switches the item URL or source.

- [ ] **Step 1: Write the failing tests**

```python
def test_external_link_post_stays_reddit():
    post = _post(
        url="https://www.youtube.com/watch?v=abc123DEF45",
        domain="youtube.com",
        is_self=False,
    )
    item = reddit_feed.post_to_reelitem(post)
    assert item.source == "reddit"
    assert item.url == post["permalink"]
    assert item.title == post["title"]
    assert item.text == post["selftext"] or item.text is None
    assert {"url": "https://www.youtube.com/watch?v=abc123DEF45", "kind": "link"} in (
        item.attachments or []
    )


def test_selftext_capped():
    post = _post(is_self=True, selftext="x" * 5000)
    item = reddit_feed.post_to_reelitem(post)
    assert len(item.text) == 2000


def test_self_post_has_no_link_attachment():
    post = _post(is_self=True, selftext="body")
    item = reddit_feed.post_to_reelitem(post)
    assert not item.attachments
```

Use/extend the existing `_post` fixture in `tests/test_reddit_feed.py`; if the current tests assert the youtube reclassification, flip those assertions in this task.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_reddit_feed.py`
Expected: FAIL — item.source == "youtube" for external posts

- [ ] **Step 3: Implement**

Rewrite `post_to_reelitem`:

```python
_TEXT_CAP = 2000


def post_to_reelitem(post: dict):
    """Map a post to a queue item. Posts always stay Reddit-native: the
    permalink is the item URL and external links ride as attachments."""
    from ytk import reels

    created = post.get("created_utc")
    shared_at = datetime.fromtimestamp(created, tz=UTC).strftime("%Y-%m-%d") if created else None
    attachments = []
    if is_external(post) and post["url"]:
        attachments.append({"url": post["url"], "kind": "link"})
    text = post["selftext"][:_TEXT_CAP] if post["selftext"] else None
    return reels.ReelItem(
        url=post["permalink"],
        author=f"r/{post['subreddit']}",
        shared_at=shared_at,
        preview_url=post["thumbnail"],
        source="reddit",
        text=text,
        title=post["title"] or None,
        attachments=attachments or None,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_reddit_feed.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ytk/reddit_feed.py tests/test_reddit_feed.py
git commit -m "feat(inbox): reddit posts queue as reddit — external links become attachments (#163)"
```

---

### Task 6: Playlist and Pinterest adapters write `title`

**Files:**
- Modify: `ytk/ui/source_refresh.py:57-104` (`pull_youtube`, `pull_pinterest`)
- Test: `tests/test_source_refresh.py`

**Interfaces:**
- Consumes: `ReelItem.title` from Task 1.
- Produces: playlist rows with `title` = video title and `author=None` (the oEmbed backfill fills the channel later — the playlist payload `{video_id, title, added_at}` carries no channel); Pinterest rows with `title` = pin title, `author=None`.

- [ ] **Step 1: Flip the encoded-bug assertions and add real-shape ones**

In `tests/test_source_refresh.py`, the existing test asserts the video title lands in `author`. Change it and add:

```python
def test_pull_youtube_stores_title_as_title():
    state = reels.ReelsState()
    videos = [{"video_id": "abc123DEF45", "title": "Video title", "added_at": "2026-08-01T00:00:00Z"}]
    source_refresh.pull_youtube(state, lambda: videos, lambda vid: False)
    row = state.pending[0]
    assert row.title == "Video title"
    assert row.author is None
    assert row.preview_url == "https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg"


def test_pull_pinterest_stores_title_as_title():
    state = reels.ReelsState()
    pins = [{"url": "https://pin.example/1", "title": "Pin title", "image": "https://img/1.jpg", "date": "2026-08-01"}]
    source_refresh.pull_pinterest(state, lambda: pins)
    row = state.pending[0]
    assert row.title == "Pin title"
    assert row.author is None
```

Match the existing tests' actual puller signatures — copy the call shape from the tests already in the file rather than the sketches above if they differ.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_source_refresh.py`
Expected: FAIL — title is None, author carries the title

- [ ] **Step 3: Implement**

In `pull_youtube`, change the `ReelItem(...)` construction: `author=video.get("title") or None` becomes `title=video.get("title") or None` (drop the author line). In `pull_pinterest`: `author=pin.get("title")` becomes `title=pin.get("title")`.

TikTok (`ytk/tiktok_fav.py:155`) and Instagram (`ytk/reels.py` extract) already store the creator handle in `author` with no title available in their payloads — correct under the tightened semantics, no change.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_source_refresh.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ytk/ui/source_refresh.py tests/test_source_refresh.py
git commit -m "fix(inbox): playlist and pinterest titles are titles, not authors (#163)"
```

---

### Task 7: Reddit ingest cross-links the linked video

**Files:**
- Modify: `ytk/reddit_feed.py` (new helper), `ytk/cli.py:1760` (`add_reddit`)
- Test: `tests/test_reddit_feed.py`

**Interfaces:**
- Consumes: `hydrate.youtube_video_id`, `db.is_processed`, the existing `add` dispatch (`cli.py:151` routes URLs), `vault.write_reddit_note`.
- Produces: `reddit_feed.external_video_url(post: dict) -> str | None` — the post's external URL when it classifies as youtube, else None. `add_reddit` gains the cross-link behavior; no signature change.

- [ ] **Step 1: Write the failing test for the helper**

```python
def test_external_video_url_detects_youtube():
    post = _post(url="https://youtu.be/abc123DEF45", domain="youtu.be", is_self=False)
    assert reddit_feed.external_video_url(post) == "https://youtu.be/abc123DEF45"


def test_external_video_url_none_for_articles():
    post = _post(url="https://blog.example.com/post", domain="blog.example.com", is_self=False)
    assert reddit_feed.external_video_url(post) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_reddit_feed.py -k external_video`
Expected: FAIL — not defined

- [ ] **Step 3: Implement the helper**

```python
def external_video_url(post: dict) -> str | None:
    from ytk import reels

    if not is_external(post):
        return None
    url = post.get("url") or ""
    return url if reels.classify_url(url) == "youtube" else None
```

- [ ] **Step 4: Wire into `add_reddit`**

In `cli.py` `add_reddit`, after the reddit note is written and indexed (after the `upsert_doc` call), add:

```python
    video_url = reddit_feed_module.external_video_url(post)
    if video_url:
        from ytk import db, hydrate

        vid = hydrate.youtube_video_id(video_url)
        if vid and not db.is_processed(vid):
            ctx = click.get_current_context()
            ctx.invoke(add, url=video_url, note=note)
        _cross_link_notes(note_path, video_url)
```

`_cross_link_notes(reddit_note: Path, video_url: str)` is a small `vault.py` function: find the youtube note whose frontmatter `url:` matches `video_url` (reuse the existing note-lookup helper if `vault.py` has one; otherwise scan `sources/youtube/*.md` frontmatter), then append a `## Related` line with a `[[wikilink]]` to each file pointing at the other, skipping the append when the wikilink is already present (idempotent). Match `add_reddit`'s actual local import names when editing — the sketch uses placeholder names; `add` is the top-level ingest command in the same module.

Test `_cross_link_notes` with two tmp-path markdown files:

```python
def test_cross_link_notes_appends_wikilinks_both_ways(tmp_path):
    reddit_note = tmp_path / "reddit-post.md"
    video_note = tmp_path / "video.md"
    reddit_note.write_text("---\nurl: https://old.reddit.com/r/x/1\n---\nbody\n")
    video_note.write_text("---\nurl: https://youtu.be/abc123DEF45\n---\nbody\n")
    vault._cross_link_notes(reddit_note, "https://youtu.be/abc123DEF45", search_dir=tmp_path)
    assert "[[video]]" in reddit_note.read_text()
    assert "[[reddit-post]]" in video_note.read_text()
    vault._cross_link_notes(reddit_note, "https://youtu.be/abc123DEF45", search_dir=tmp_path)
    assert reddit_note.read_text().count("[[video]]") == 1
```

Give `_cross_link_notes` a `search_dir: Path | None = None` parameter defaulting to the vault's `sources/youtube/` directory so the test can point it at tmp_path.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest -q tests/test_reddit_feed.py tests/test_vault.py -k "external_video or cross_link"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ytk/reddit_feed.py ytk/cli.py ytk/vault.py tests/
git commit -m "feat(ingest): reddit posts also ingest their linked video, cross-linked (#163)"
```

---

### Task 8: Cover repair and observability

**Files:**
- Modify: `ytk/ui/hub.py:852-886` (`_download_cover`, `cover_for`; new `cover_invalidate`), `ytk/reels.py` (`refresh` merge, around `reels.py:338-347`)
- Test: `tests/test_hub_queue.py` (or the existing cover-cache test file — check `grep -rl cover_for tests/`), `tests/test_reels.py`

**Interfaces:**
- Consumes: cover key scheme `sha1(item_url)[:20] + ".jpg"` in `COVERS_DIR`.
- Produces: `cover_invalidate(item_url: str) -> None` — unlinks the cached cover; called by Task 4's backfill when hydration changed `preview_url`. `cover_for` logs failures via `logging.getLogger("ytk.hub")` with item URL, delivery host, and exception class. `reels.refresh` updates `preview_url` on rediscovered rows (all other fields preserved; cached covers not touched, so present covers survive and missing ones repair on next request).

- [ ] **Step 1: Write the failing tests**

```python
def test_cover_for_logs_failures(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(hub, "COVERS_DIR", tmp_path)
    monkeypatch.setattr(
        hub, "queue_items",
        lambda: [reels.ReelItem(url="https://x/1", preview_url="https://dead.host/i.jpg")],
    )

    def boom(url, dest):
        raise OSError("dns failure")

    monkeypatch.setattr(hub, "DOWNLOAD_COVER", boom)
    with caplog.at_level("WARNING", logger="ytk.hub"):
        assert hub.cover_for("https://x/1") is None
    record = caplog.records[0].getMessage()
    assert "https://x/1" in record
    assert "dead.host" in record
    assert "OSError" in record


def test_cover_invalidate_unlinks(monkeypatch, tmp_path):
    monkeypatch.setattr(hub, "COVERS_DIR", tmp_path)
    import hashlib

    key = hashlib.sha1(b"https://x/1", usedforsecurity=False).hexdigest()[:20] + ".jpg"
    (tmp_path / key).write_bytes(b"old")
    hub.cover_invalidate("https://x/1")
    assert not (tmp_path / key).exists()


def test_refresh_updates_preview_url_on_rediscovery():
    clip = SimpleNamespace(code="aaa", thumbnail_url="https://cdn.example/new.jpg")
    msg = SimpleNamespace(
        id="9", item_type="clip", clip=clip,
        user_id="7", timestamp=None,
    )
    client = _client_with_thread([msg])
    state = reels.ReelsState(
        thread_id="ts",
        pending=[
            reels.ReelItem(
                url="https://www.instagram.com/reel/aaa/",
                author="someone",
                title="Kept title",
                preview_url="https://instagram.ftpa1-1.fna.fbcdn.net/old.jpg",
            )
        ],
    )
    refreshed = reels.refresh(client, state)
    assert len(refreshed.pending) == 1
    row = refreshed.pending[0]
    assert row.preview_url == "https://cdn.example/new.jpg"
    assert row.author == "someone"
    assert row.title == "Kept title"
```

The message shape above is a sketch of the `_clip` fixture already in `tests/test_reels.py` — reuse that fixture and the `_client_with_thread` helper (`tests/test_reels.py:119`) rather than hand-rolling the SimpleNamespace, keeping only the new-thumbnail override and the assertions.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_hub_queue.py tests/test_reels.py -k "cover or rediscovery"`
Expected: FAIL

- [ ] **Step 3: Implement**

In `cover_for`'s except branch:

```python
    except Exception as exc:
        dest.unlink(missing_ok=True)
        host = urllib.parse.urlsplit(preview).netloc
        _LOG.warning("cover download failed item=%s host=%s error=%s: %s",
                     item_url, host, type(exc).__name__, exc)
        return None
```

with `_LOG = logging.getLogger("ytk.hub")` at module top. Add:

```python
def cover_invalidate(item_url: str) -> None:
    import hashlib

    key = hashlib.sha1(item_url.encode(), usedforsecurity=False).hexdigest()[:20] + ".jpg"
    (COVERS_DIR / key).unlink(missing_ok=True)
```

Wire `cover_invalidate` into Task 4's `hydrate_pending` (the `changed` branch) and Task 3's enqueue path. In `reels.refresh`, where existing pending entries currently win wholesale, merge instead:

```python
    known = {i.url: i for i in existing}
    for incoming in items:
        held = known.get(incoming.url)
        if held is not None and incoming.preview_url:
            held.preview_url = incoming.preview_url
    new_state.pending = [*existing, *[i for i in items if i.url not in known]]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_hub_queue.py tests/test_reels.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ytk/ui/hub.py ytk/reels.py tests/
git commit -m "fix(inbox): observable cover failures, refreshable previews (#163)"
```

---

### Task 9: Frontend — title semantics and provenance de-echo

**Files:**
- Modify: `web/src/api/queue.ts` (QueueItem type), `web/src/components/Card.tsx:295` (title slot, `itemLabel`), `web/src/lib/provenance.ts` (platform label suppression)
- Test: `web/src/components/Card.test.tsx`, `web/src/lib/provenance.test.ts`

**Interfaces:**
- Consumes: queue API rows now carrying `title` and `attachments` (the FastAPI route serializes the dataclass; new fields flow through unchanged).
- Produces: `QueueItem` gains `title?: string | null` and `attachments?: {url: string; kind: string}[] | null`. Card title slot renders `item.title || excerpt(item.text) ||` a neutral `untitled` span (class `card-untitled`, styled via existing Tailwind utilities — CSS budget forbids new styles.css rules). Provenance: for first-party platform domains (`youtube.com`, `youtu.be`, `instagram.com`, `tiktok.com`, `pinterest.com`), `label` is the community when one is named, else empty — so `CardMeta`'s existing `place !== source` check drops the echo.

- [ ] **Step 1: Flip the encoded-bug test and add real-shape fixtures**

In `provenance.test.ts`, the test expecting `youtube.com` as a label changes to expect `""`. Add:

```ts
test("platform domains yield no label without a community", () => {
  expect(provenance("https://www.youtube.com/watch?v=abc").label).toBe("");
  expect(provenance("https://www.instagram.com/reel/XYZ/").label).toBe("");
});

test("reddit still yields its community", () => {
  expect(provenance("https://old.reddit.com/r/rust/comments/1/x/").label).toBe("r/rust");
});

test("generic web keeps its domain", () => {
  expect(provenance("https://blog.example.com/post").label).toBe("blog.example.com");
});
```

In `Card.test.tsx`, add a real-shape playlist row (`text: null`, `title` set) and assert the title renders exactly once; add a titleless, textless row and assert the neutral state appears and the raw URL does not:

```ts
test("playlist row renders its title once, no hostname echo", () => {
  render(<Card item={{ url: "https://www.youtube.com/watch?v=abc", source: "youtube", title: "Attention is all you need", text: null }} />);
  expect(screen.getAllByText("Attention is all you need")).toHaveLength(1);
  expect(screen.queryByText("youtube.com")).not.toBeInTheDocument();
});

test("bare row shows neutral state, never the URL as a heading", () => {
  render(<Card item={{ url: "https://www.youtube.com/watch?v=abc", source: "youtube", text: null }} />);
  expect(screen.getByText("untitled")).toBeInTheDocument();
});
```

Match the existing tests' render helper and required props — copy their setup.

- [ ] **Step 2: Run to verify failure**

Run: `cd web && vp exec vitest run src/lib/provenance.test.ts src/components/Card.test.tsx`
Expected: FAIL

- [ ] **Step 3: Implement**

`queue.ts`: add the two optional fields to the type. `provenance.ts`: add

```ts
const FIRST_PARTY = ["youtube.com", "youtu.be", "instagram.com", "tiktok.com", "pinterest.com"];

// inside provenance():
const firstParty = FIRST_PARTY.some((d) => domain === d || domain.endsWith(`.${d}`));
return { domain, ...(named ? { community: named } : {}), label: named ?? (firstParty ? "" : domain) };
```

`Card.tsx` title slot:

```tsx
<div className="title">
  {item.title || excerpt(item.text) || <span className="card-untitled">untitled</span>}
</div>
```

Update `itemLabel` to prefer `item.title` first, and keep the URL out of the visible heading (it may remain in the accessible label only if nothing else exists).

- [ ] **Step 4: Run to verify pass**

Run: `cd web && vp exec vitest run src/lib/provenance.test.ts src/components/Card.test.tsx src/components/QueueItemViewer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/api/queue.ts web/src/components/Card.tsx web/src/lib/provenance.ts web/src/lib/provenance.test.ts web/src/components/Card.test.tsx
git commit -m "fix(inbox): titles are titles on cards; platform hostname echo removed (#163)"
```

---

### Task 10: Full gate and close-out

**Files:**
- No new code. Verification and bookkeeping only.

- [ ] **Step 1: Run the complete repository gate**

Run: `just check`
Expected: PASS. Check RAM first (`memory_pressure | head -1`) — if the machine is under pressure, run the Python and frontend halves separately.

- [ ] **Step 2: Reinstall and live-verify**

```bash
uv tool install --reinstall .
launchctl kickstart -k gui/501/com.ytk.hub
```

Then check `/api/ingest/status` is idle before the kickstart. Paste a YouTube URL into the hub Add box; confirm the card shows real title + thumbnail. Trigger a refresh; confirm reddit-sourced rows keep `source=reddit` and backfill starts stamping `hydrated_at` (inspect `~/.ytk/reels_state.json`).

- [ ] **Step 3: Commit any stragglers, push**

```bash
git status
git push
```
