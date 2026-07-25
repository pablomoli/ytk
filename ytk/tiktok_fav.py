# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""TikTok favorites discovery via session replay of the user's own web session.

TikTok signs its web API params (X-Bogus) in page JavaScript, so request-forging
libraries cannot list private favorites. This module never forges a request: a
headless Playwright Firefox loads the favorites tab with session cookies read
from the Zen browser profile, TikTok's own JS makes the signed
/api/user/favorite/item_list/ calls while we scroll, and the JSON responses are
read off the wire. Validity is inherited, not forged.

Same risk posture as the instagrapi fetcher: the user's real account, read-only,
gentle cadence (daily by default, see HubConfig.cadence_minutes).
"""

from __future__ import annotations

import random
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:  # playwright is imported lazily where it is used
    # Not re-exported from playwright.sync_api, so this reaches into _impl.
    # Type-only: if playwright moves it, pyright says so at check time and
    # nothing changes at runtime.
    from playwright._impl._api_structures import SetCookieParam

ZEN_PROFILES = Path.home() / "Library" / "Application Support" / "zen" / "Profiles"

_SAMESITE = {0: "None", 1: "Lax", 2: "Strict"}

# Scrolls with no new favorites before concluding the list is exhausted. The
# grid lazy-loads unevenly, so a single quiet scroll is not the end.
_QUIET_SCROLLS = 4

# The favorites grid is fed by this XHR (TikTok renamed it from the older
# favorite/item_list; the JSON shape is unchanged). Matching the response is
# markup-independent — selectors only need to get the tab open and scrolling.
_FAV_ENDPOINT = "collect/item_list"


class TikTokAuthError(RuntimeError):
    """Session cookies are missing or logged out."""


def zen_cookie_db(profiles_dir: Path = ZEN_PROFILES) -> Path:
    """Newest cookies.sqlite across Zen profiles (Zen is Firefox-based)."""
    candidates = sorted(
        profiles_dir.glob("*/cookies.sqlite"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise TikTokAuthError(
            f"No Zen cookie database found under {profiles_dir}. "
            "Is Zen installed and has it been opened at least once?"
        )
    return candidates[0]


def _norm_expiry(expiry) -> float:
    """Cookie expiry → Playwright's contract: -1 (session) or unix seconds.

    Firefox stores session cookies as 0, and TikTok writes ms-epoch expiries
    (~1.8e12, year 58k if read as seconds) that Playwright rejects outright.
    """
    exp = float(expiry or 0)
    if exp > 1e11:
        exp /= 1000.0
    return exp if exp > 0 else -1.0


def load_tiktok_cookies(db: Path) -> list[SetCookieParam]:
    """Read tiktok.com cookies from a Firefox-format cookie DB.

    The DB is copied first: the browser holds a lock on the live file, and a
    read-only open can still fail mid-vacuum.
    """
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "cookies.sqlite"
        shutil.copy2(db, copy)
        con = sqlite3.connect(copy)
        try:
            rows = con.execute(
                "SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite"
                " FROM moz_cookies WHERE host LIKE '%tiktok.com'"
            ).fetchall()
        finally:
            con.close()
    # cast per row: a comprehension infers a plain dict, and SetCookieParam is
    # total=False, so the keys below are exactly the ones playwright reads.
    cookies: list[SetCookieParam] = [
        cast(
            "SetCookieParam",
            {
                "name": name,
                "value": value,
                "domain": host,
                "path": path,
                "expires": _norm_expiry(expiry),
                "secure": bool(secure),
                "httpOnly": bool(http_only),
                "sameSite": _SAMESITE.get(same_site, "Lax"),
            },
        )
        for name, value, host, path, expiry, secure, http_only, same_site in rows
    ]
    if not any(c.get("name") == "sessionid" for c in cookies):
        raise TikTokAuthError(
            "No tiktok.com sessionid cookie in the Zen profile. "
            "Log into tiktok.com in Zen, then retry."
        )
    return cookies


def parse_favorites_response(data: dict) -> list[dict]:
    """Extract favorite items from one /api/user/favorite/item_list/ response.

    Tolerates missing authors (deleted accounts) and photo-mode posts; the
    canonical @_/video/{id} URL resolves regardless of author handle.
    """
    items = []
    for entry in data.get("itemList") or []:
        video_id = str(entry.get("id") or "").strip()
        if not video_id:
            continue
        author = (entry.get("author") or {}).get("uniqueId") or "_"
        video = entry.get("video") or {}
        items.append(
            {
                "id": video_id,
                "url": f"https://www.tiktok.com/@{author}/video/{video_id}",
                "author": author if author != "_" else None,
                "desc": (entry.get("desc") or "").strip() or None,
                "cover": video.get("cover") or None,
                "create_time": entry.get("createTime"),
            }
        )
    return items


def favorites_to_reelitems(items: list[dict]) -> list:
    from ytk import reels

    out = []
    for it in items:
        out.append(
            reels.ReelItem(
                url=it["url"],
                author=it.get("author"),
                shared_at=time.strftime("%Y-%m-%d"),
                preview_url=it.get("cover"),
                source="tiktok",
                text=it.get("desc"),
            )
        )
    return out


def queue_new(state, fetched: list[dict], extra_known: set | frozenset = frozenset()) -> int:
    """Append unseen favorites to the pending queue, marking all ids seen.

    Every fetched id lands in state.tiktok_seen (so the next sync stops early)
    even when the URL is deduped against the queue or already-ingested notes.
    """
    known = {i.url for i in state.pending} | set(extra_known)
    added = 0
    for item in favorites_to_reelitems(fetched):
        state.tiktok_seen.append(item.url.rsplit("/", 1)[-1])
        if item.url in known:
            continue
        state.pending.append(item)
        added += 1
    return added


def fetch_favorites(
    username: str,
    cookies: list[SetCookieParam],
    seen: frozenset | set = frozenset(),
    max_pages: int | None = None,
    headed: bool = False,
    pause: float = 1.8,
) -> list[dict]:
    """Scroll the user's favorites tab and collect intercepted item pages.

    Stops when a whole response page is already in `seen` (incremental sync —
    favorites are newest-first), when the grid stops yielding new items, or at
    `max_pages`. Never opens the user's own browser; Playwright runs its own
    Firefox, headless unless `headed`.
    """
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    collected: dict[str, dict] = {}
    state = {"pages": 0, "all_seen": False}

    def on_response(resp) -> None:
        if _FAV_ENDPOINT not in resp.url:
            return
        try:
            batch = parse_favorites_response(resp.json())
        except Exception:
            return
        if not batch:
            return
        state["pages"] += 1
        if all(it["id"] in seen for it in batch):
            state["all_seen"] = True
        for it in batch:
            collected.setdefault(it["id"], it)

    with sync_playwright() as pw:
        browser = pw.firefox.launch(headless=not headed)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        page.on("response", on_response)
        page.goto(f"https://www.tiktok.com/@{username}", wait_until="networkidle")
        try:
            # The Favorites tab is owner-only, so finding it doubles as the
            # login check. Located by visible label rather than a data-e2e
            # attribute — the attribute is absent on the current markup while
            # the label is stable.
            page.get_by_text("Favorites", exact=True).first.click(timeout=15000)
        except PWTimeout as exc:
            browser.close()
            raise TikTokAuthError(
                "Favorites tab not found — the session is likely logged out, or "
                "the profile has no favorites. Log into tiktok.com in Zen "
                "(cookies refresh on browsing), then retry."
            ) from exc

        quiet = 0
        while True:
            before = len(collected)
            page.mouse.wheel(0, 4000)
            time.sleep(pause * (0.75 + random.random() * 0.5))
            if state["all_seen"]:
                break
            if max_pages is not None and state["pages"] >= max_pages:
                break
            quiet = quiet + 1 if len(collected) == before else 0
            if quiet >= _QUIET_SCROLLS:
                break
        browser.close()

    return [it for it in collected.values() if it["id"] not in seen]
