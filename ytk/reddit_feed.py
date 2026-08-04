# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Reddit subreddit-feed discovery via the user's logged-in session.

The sign-free flavor of the Zen-session ingestion primitive: Reddit does not
sign its requests, so a plain authenticated JSON GET (cookie read from the Zen
profile) is enough — no headless browser. In 2026 Reddit 403s unauthenticated
.json, so the session cookie is what unlocks reading subreddits at all.

PRIVACY BOUNDARY (load-bearing, do not weaken): this module reads PUBLIC
subreddit listings from a configured allowlist ONLY. Every request URL is built
as https://old.reddit.com/r/<subreddit>/... from a name validated against
_SUBREDDIT_RE. There is deliberately no function that takes a username and no
code path that can construct a /user/ or /saved endpoint. The user's saved
posts are never read.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
import urllib.parse
import urllib.request
from datetime import UTC
from pathlib import Path

from ytk.tiktok_fav import zen_cookie_db

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:141.0) Gecko/20100101 Firefox/141.0"

# A subreddit name is the ONLY user-supplied value that reaches a URL path, so
# it is validated to alphanumeric + underscore — structurally unable to express
# "user", a slash, "..", or a "/saved" segment.
_SUBREDDIT_RE = re.compile(r"[A-Za-z0-9_]{2,50}")
_SORTS = {"hot", "top", "new", "rising"}
_WINDOWS = {"hour", "day", "week", "month", "year", "all"}

# Domains that mean "the content lives on Reddit" — these route through the
# Reddit ingest handler (selftext / comments / reddit-hosted media). Anything
# else is an external link and ingests through its own native ytk path.
_REDDIT_DOMAINS = {"i.redd.it", "v.redd.it", "reddit.com", "www.reddit.com", "old.reddit.com"}


class RedditAuthError(RuntimeError):
    """The Zen session has no usable reddit_session cookie."""


def _validate_subreddit(name: str) -> str:
    if not _SUBREDDIT_RE.fullmatch(name or ""):
        raise ValueError(f"Invalid subreddit name: {name!r}")
    return name


def reddit_cookie_header(db: Path | None = None) -> str:
    """Build a Cookie header from the Zen profile's reddit.com cookies."""
    db = db or zen_cookie_db()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "cookies.sqlite"
        shutil.copy2(db, copy)
        con = sqlite3.connect(copy)
        try:
            rows = con.execute(
                "SELECT name, value FROM moz_cookies WHERE host LIKE '%reddit.com'"
            ).fetchall()
        finally:
            con.close()
    names = {n for n, _ in rows}
    if "reddit_session" not in names:
        raise RedditAuthError(
            "No reddit_session cookie in the Zen profile. Log into reddit.com in "
            "Zen (cookies refresh on browsing), then retry."
        )
    return "; ".join(f"{n}={v}" for n, v in rows)


def _get(url: str, cookie_header: str) -> dict | list:
    """Parsed JSON. Listing endpoints return an object; a post permalink
    returns a two-element array, so callers narrow to what they asked for."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Cookie": cookie_header})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read())


def fetch_listing(
    subreddit: str,
    cookie_header: str,
    sort: str = "top",
    window: str = "week",
    limit: int = 25,
) -> dict:
    """Fetch one subreddit listing. URL is /r/<sub>/ only, never /user/ or /saved."""
    sub = _validate_subreddit(subreddit)
    if sort not in _SORTS:
        raise ValueError(f"Unsupported sort: {sort!r}")
    params = {"limit": str(limit), "raw_json": "1"}
    if sort == "top":
        if window not in _WINDOWS:
            raise ValueError(f"Unsupported window: {window!r}")
        params["t"] = window
    url = f"https://old.reddit.com/r/{sub}/{sort}.json?{urllib.parse.urlencode(params)}"
    listing = _get(url, cookie_header)
    return listing if isinstance(listing, dict) else {}


def parse_posts(listing: dict) -> list[dict]:
    """Flatten a listing response into post dicts (t3 children only)."""
    posts = []
    for child in (listing.get("data") or {}).get("children") or []:
        if child.get("kind") != "t3":
            continue
        d = child.get("data") or {}
        pid = d.get("id")
        permalink = d.get("permalink")
        if not pid or not permalink:
            continue
        thumb = d.get("thumbnail") or ""
        posts.append(
            {
                "id": pid,
                "fullname": d.get("name") or f"t3_{pid}",
                "permalink": f"https://old.reddit.com{permalink}",
                "title": (d.get("title") or "").strip(),
                "subreddit": d.get("subreddit") or "",
                "author": d.get("author") or "[deleted]",
                "score": d.get("score") or 0,
                "num_comments": d.get("num_comments") or 0,
                "is_self": bool(d.get("is_self")),
                "selftext": (d.get("selftext") or "").strip(),
                "url": d.get("url_overridden_by_dest") or d.get("url") or "",
                "domain": (d.get("domain") or "").lower(),
                "thumbnail": thumb if thumb.startswith("http") else None,
                "created_utc": d.get("created_utc"),
                "over_18": bool(d.get("over_18")),
            }
        )
    return posts


def is_external(post: dict) -> bool:
    """A link post to non-Reddit content, ingestible through a native ytk path."""
    if post["is_self"]:
        return False
    domain = post["domain"]
    if domain.startswith("self."):
        return False
    return domain not in _REDDIT_DOMAINS


def external_video_url(post: dict) -> str | None:
    """The post's external URL when it's a link to a YouTube video, else None."""
    from ytk import reels

    if not is_external(post):
        return None
    url = post.get("url") or ""
    return url if reels.classify_url(url) == "youtube" else None


_TEXT_CAP = 2000


def post_to_reelitem(post: dict):
    """Map a post to a queue item. Posts always stay Reddit-native: the
    permalink is the item URL and external links ride as attachments."""
    from datetime import datetime

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


def sync_subreddits(
    state,
    cookie_header: str,
    subreddits: list[str],
    sort: str = "top",
    window: str = "week",
    limit: int = 25,
    extra_known: set | frozenset = frozenset(),
) -> int:
    """Drain the allowlisted subreddits into the pending queue.

    Dedup is by post fullname against state.reddit_seen (so re-syncs skip posts
    already seen), the current queue, and extra_known (already-ingested urls).
    Every seen fullname is recorded even when its url is a dup, so the set
    converges. One failed subreddit does not sink the rest.
    """
    seen = set(state.reddit_seen)
    known_urls = {i.url for i in state.pending} | set(extra_known)
    added = 0
    for sub in subreddits:
        try:
            listing = fetch_listing(sub, cookie_header, sort=sort, window=window, limit=limit)
        except Exception:
            continue
        for post in parse_posts(listing):
            if post["fullname"] in seen:
                continue
            seen.add(post["fullname"])
            state.reddit_seen.append(post["fullname"])
            item = post_to_reelitem(post)
            if item.url in known_urls:
                continue
            known_urls.add(item.url)
            state.pending.append(item)
            added += 1
    return added


def search_subreddits(query: str, cookie_header: str, limit: int = 10) -> list[dict]:
    """Reddit's subreddit search — the 'find related communities' discovery feature."""
    url = "https://old.reddit.com/subreddits/search.json?" + urllib.parse.urlencode(
        {"q": query, "limit": str(limit), "raw_json": "1"}
    )
    out = []
    found = _get(url, cookie_header)
    listing = found if isinstance(found, dict) else {}
    for child in (listing.get("data") or {}).get("children") or []:
        d = child.get("data") or {}
        name = d.get("display_name")
        if not name:
            continue
        out.append(
            {
                "name": name,
                "subscribers": d.get("subscribers") or 0,
                "description": (d.get("public_description") or "").strip(),
                "over_18": bool(d.get("over18")),
            }
        )
    return out


def fetch_comments(permalink: str, cookie_header: str, limit: int = 60) -> list:
    """Fetch a post thread. Only accepts our own /r/ permalinks (guardrail)."""
    path = urllib.parse.urlparse(permalink).path
    if not path.startswith("/r/"):
        raise ValueError(f"Refusing non-/r/ permalink: {permalink!r}")
    url = f"https://old.reddit.com{path.rstrip('/')}.json?" + urllib.parse.urlencode(
        {"limit": str(limit), "raw_json": "1"}
    )
    thread = _get(url, cookie_header)
    return thread if isinstance(thread, list) else []


def top_comments(thread: list, n: int = 6, min_score: int = 1) -> list[dict]:
    """Top-scoring real comments from a thread response, bots/mods removed."""
    if not isinstance(thread, list) or len(thread) < 2:
        return []
    children = (thread[1].get("data") or {}).get("children") or []
    comments = []
    for c in children:
        if c.get("kind") != "t1":
            continue
        d = c.get("data") or {}
        body = (d.get("body") or "").strip()
        author = d.get("author") or ""
        if not body or body in ("[deleted]", "[removed]"):
            continue
        if author.lower() in ("automoderator", "[deleted]") or d.get("stickied"):
            continue
        if (d.get("score") or 0) < min_score:
            continue
        comments.append({"author": author, "score": d.get("score") or 0, "body": body})
    comments.sort(key=lambda x: x["score"], reverse=True)
    return comments[:n]


def post_from_thread(thread: list) -> dict | None:
    """The originating post (t3) from a thread response."""
    posts = parse_posts(thread[0]) if isinstance(thread, list) and thread else []
    return posts[0] if posts else None


def build_content_block(post: dict, comments: list[dict]) -> str:
    """Compose the enrichment input: post framing, body/link, then discussion."""
    lines = [
        f"Subreddit: r/{post['subreddit']}",
        f"Title: {post['title']}",
        f"Posted by u/{post['author']} | Score: {post['score']} | {post['num_comments']} comments",
    ]
    if post["is_self"]:
        lines += ["", "Body:", post["selftext"] or "(no body text)"]
    else:
        lines += ["", f"Links to: {post['url']} ({post['domain']})"]
    if comments:
        lines += ["", "Top comments:"]
        for c in comments:
            lines.append(f"- u/{c['author']} ({c['score']}): {c['body']}")
    return "\n".join(lines)
