"""Fill a queue item's missing metadata from its URL.

oEmbed for YouTube, Open Graph tags for the general web. Fetchers are
injectable so tests never touch the network.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date
from html.parser import HTMLParser
from typing import Any

from ytk import reels

_YT_ID_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/)|youtu\.be/)([\w-]{11})")
_UA = {"User-Agent": "Mozilla/5.0"}
_READ_CAP = 512 * 1024


def youtube_video_id(url: str) -> str | None:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def default_fetch_json(url: str) -> dict[str, Any]:
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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag != "meta":
            return
        a = dict(attrs)
        key = a.get("property") or a.get("name") or ""
        content = a.get("content") or ""
        if key and content and key not in self.meta:
            self.meta[key] = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.title:
            self.title = data.strip()


def _web_fields(html: str) -> dict[str, str | None]:
    p = _HeadParser()
    p.feed(html)
    m = p.meta
    return {
        "title": m.get("og:title") or m.get("twitter:title") or p.title or None,
        "preview_url": m.get("og:image") or m.get("twitter:image") or None,
        "text": m.get("og:description") or m.get("twitter:description") or None,
    }


def _youtube_fields(url: str, fetch_json: Callable[[str], dict[str, Any]]) -> dict[str, str | None]:
    oembed = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": url, "format": "json"}
    )
    data = fetch_json(oembed)
    return {
        "title": data.get("title") or None,
        "author": data.get("author_name") or None,
        "preview_url": data.get("thumbnail_url") or None,
    }


def hydrate_item(
    item: reels.ReelItem,
    *,
    fetch_json: Callable[[str], dict[str, Any]] = default_fetch_json,
    fetch_html: Callable[[str], str] = default_fetch_html,
) -> bool:
    """Mutate item in place; return True when preview_url changed."""
    old_preview = item.preview_url
    item.hydrated_at = date.today().isoformat()
    item.hydrate_error = None
    kind = reels.classify_url(item.url)
    # No authenticated fetcher exists for these: an unauthenticated GET returns
    # login-page junk and would clobber a signed CDN preview_url. Still stamp
    # hydrated_at so these rows don't eat the backfill budget every cycle.
    if kind in ("instagram", "tiktok"):
        return item.preview_url != old_preview
    fields: dict[str, str | None] = {}
    try:
        if kind == "youtube":
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
