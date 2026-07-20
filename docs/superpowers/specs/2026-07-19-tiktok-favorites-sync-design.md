# TikTok favorites sync — design

Date: 2026-07-19. Status: approved in session (user: "i really just want to get the
tiktok one working. and ingest those."). Research basis:
`docs/research/2026-07-19-ingestion-sources.md`.

## Problem

The user has ~2,485 favorited TikToks and wants them discovered into the ytk pending
queue automatically — recurring, never a manual data-export ritual. No API, library,
or export flow can list private favorites programmatically; the only live path is the
user's own web session.

## Approach: session replay with response interception

TikTok signs its web API params (X-Bogus) in page JavaScript, which is why request-
forging libraries fail. We never forge: a headless Playwright Firefox loads the
user's favorites page with session cookies read from the Zen browser profile, TikTok's
own JS makes the signed `/api/user/favorite/item_list/` calls while we scroll, and we
read the JSON responses off the wire. Validity is inherited, not forged. This mirrors
the house-precedent risk posture of the instagrapi fetcher (real account, read-only,
gentle cadence).

Rejected alternatives: data export (snapshot-only, manual ritual — vetoed by user);
TikTokApi (no user-authenticated routes, cannot see private favorites); official
Display/Research APIs (no favorites endpoint / academics only); Data Portability API
(EEA/UK only).

## Components

### `ytk/tiktok_fav.py` (new)
- `zen_cookie_db() -> Path` — newest `~/Library/Application Support/zen/Profiles/*/cookies.sqlite`.
- `load_tiktok_cookies(db) -> list[dict]` — copy the sqlite (Zen holds a lock), read
  `moz_cookies` for `%.tiktok.com`, map to Playwright cookie dicts (sameSite int → enum).
- `parse_favorites_response(data) -> list[dict]` — `itemList[]` → `{id, url, author,
  desc, cover, create_time}`; URL is `https://www.tiktok.com/@{author}/video/{id}`.
- `fetch_favorites(username, cookies, seen, max_pages=None, headed=False) -> list[dict]`
  — Playwright Firefox (headless by default, never opens the user's browser), attach a
  response listener for `favorite/item_list`, open `tiktok.com/@{username}`, click the
  favorites tab, scroll with human-ish pacing until: no new items for a few scrolls,
  every id in a page is already `seen` (incremental stop), or `max_pages`. Raises a
  clear error naming the cookie-refresh fix if the session is logged out.
- Thin shell: all parsing/stop logic is in pure functions; Playwright driving stays
  minimal and untested.

### `ytk/reels.py`
- `ReelsState.tiktok_seen: list[str]` — favorited video ids already queued/ingested.
  Favorites are newest-first, so the daily incremental run usually stops after one
  page. A full id list (not a single cursor) survives unfavoriting the newest item.

### `ytk/ui/hub.py`
- `_tt_pull(state) -> int` + `TT_PULL` test seam, registered in `refresh_sources()`
  beside instagram/youtube/pinterest/imessage with independent failure isolation.
- Result dict gains a `"tiktok"` count.

### `ytk/config.py`
- `Config.tiktok_username: str | None` (sync disabled when unset).
- `HubConfig.cadence_minutes` default gains `"tiktok": 1440` — daily, not the 15-min
  fallback; favorites-page scraping on every hub page load is bot-shaped traffic.

### `ytk/cli.py`
- `ytk tiktok-sync [--pages N] [--headed]` — manual/backfill entry point; drains new
  favorites into the pending queue and prints the count. First run walks all ~2,485.

### `pyproject.toml`
- `playwright` dependency; one-time `uv run playwright install firefox`.

## Data flow

zen cookies → playwright favorites scroll → parse responses → dedupe (tiktok_seen ∪
pending urls ∪ ingested_urls()) → `ReelItem(url, author, text=desc,
preview_url=cover, source="tiktok")` → pending queue → /inbox picker → existing
`add-tiktok` ingest (yt-dlp + whisper + frames + Haiku) — zero new ingest code.

## Error handling

- Logged-out session: explicit error telling the user to log into tiktok.com in Zen
  (cookies refresh on browsing; no token dance).
- Zen profile locked/missing: copy-then-read; clear error if no profile found.
- Each hub pull is failure-isolated per the existing registry contract.
- Dead/deleted videos surface at ingest time via add-tiktok's per-item failure logging,
  not at discovery.

## Testing

Pure-function tests (pytest, fixtures): favorites-response parsing (fixture JSON incl.
missing-author and photo-mode items), cookie-db reading (throwaway sqlite with
moz_cookies schema), ReelsState round-trip with `tiktok_seen`, `_tt_pull` via seam
(fake fetch, assert queue append + seen update + dedupe). Playwright shell excluded.

## Explicit non-goals

- Bulk auto-ingest of the backlog (2,485 items × ~2 min ≈ 80+ hours of whisper +
  enrichment) — the user triages from the inbox; batch strategy decided separately.
- X/Twitter (dropped), Reddit, HN, Spotify — parked in the research doc.
- Liked-videos tab, watch history, collections — favorites only.

## Risks

- TikTok bot detection on headless browsers can soft-block a session: mitigate with
  real cookies, human-ish scroll pacing, daily cadence. Fallback if flaky: in-page
  userscript in Zen POSTing new favorites to the hub.
- Markup drift on the favorites tab selector (`data-e2e` attributes are the stable
  choice); response interception is markup-independent once scrolling works.
