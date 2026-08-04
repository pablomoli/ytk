# Inbox item normalization — schema, hydration, and Reddit nativity

Date: 2026-08-04
Status: approved (approach A of three considered)
Issues: #163 (core + IG preview repair; caption capture deferred), new
implementation issue for hydration + Reddit routing

## Problem

The pending queue (`~/.ytk/reels_state.json`, `ReelItem` in `ytk/reels.py`)
has no `title` field, so every discovery adapter overloads other slots:

- YouTube playlist refresh stores the video title in `author`
  (`ytk/ui/source_refresh.py`), so cards render the title twice.
- Reddit sync reclassifies external-link posts as their target source
  (`ytk/reddit_feed.py: is_external`), producing "youtube" items wearing
  Reddit metadata: post title in `text`, `r/sub` in `author`, Reddit's
  ~140px thumbnail in `preview_url`.
- The hub paste box (`reels.add_urls`) enqueues url + source only; those
  cards render a raw URL as title and no cover, even for YouTube URLs
  whose thumbnail is derivable offline.
- Instagram preview URLs are signed, ephemeral CDN links persisted as if
  durable; a broken host becomes a permanent silent 404 because
  `hub.cover_for` swallows errors and rediscovery never overwrites an
  existing row's `preview_url`.

Full investigation with live-queue evidence: issue #163.

## Decisions (user-confirmed)

1. Evolve `ReelItem` in place (approach A). No per-source model split, no
   render-side-only fix.
2. Reddit posts stay Reddit. No reclassification to the linked target.
   On ingest, an external YouTube link is ingested additionally as its
   own note, cross-linked both ways.
3. Schema gains an `attachments` list now (Reddit galleries/media).
4. Hydration (oEmbed for YouTube, Open Graph for web) runs at enqueue
   for new items plus a throttled newest-first backfill over the ~4k
   existing pending items inside the existing refresh cycle.
5. Scope: #163 core (schema, adapters, card semantics) plus refreshable
   IG previews and cover-failure observability. Instagram caption
   capture is deferred (needs extra instagrapi calls).

## Schema

`ReelItem` (`ytk/reels.py`) gains:

- `title: str | None` — content title. Never a creator handle, never a
  URL.
- `attachments: list[dict] | None` — `{url: str, kind: "image" |
  "video" | "link"}`. `preview_url` remains the single card cover.
- `hydrated_at: str | None` — ISO date stamped when hydration ran,
  success or permanent failure.
- `hydrate_error: str | None` — set on permanent failure so the
  backfill never re-fetches a dead URL.

Existing fields, semantics tightened:

- `author` — creator provenance only (channel, username, `r/sub`).
- `text` — body/caption only (Reddit selftext capped per the #132
  lesson, iMessage body). Never a title.
- `preview_url` — documented ephemeral/refreshable; rediscovery and
  hydration may overwrite it.

Migration: none needed at load. `_as_item` already defaults missing
keys; old state files load unchanged. Field repair happens through the
backfill (below), not a migration script.

## Adapters (discovery-time constructors)

- Playlist refresh (`source_refresh.pull_youtube`): `title` = video
  title, `author` = channel when the playlist payload carries it,
  `preview_url` = derived `i.ytimg.com/vi/{id}/hqdefault.jpg` (existing
  behavior, kept).
- Reddit (`reddit_feed.post_to_reelitem`): always `source="reddit"`,
  `url` = permalink, `title` = post title, `text` = selftext (capped),
  `author` = `r/sub`, gallery/media/external links into `attachments`
  (external links as `kind: "link"`). `is_external` routing removed.
- Paste box / web (`reels.add_urls`): enqueue sparse, then hydrate.
- Pinterest: pin title moves from `author` to `title`.
- Instagram/TikTok/iMessage: fields mapped to the tightened semantics;
  no new fetching.

## Hydrator

New module `ytk/hydrate.py`, two strategies keyed off `classify_url`:

- YouTube: `https://www.youtube.com/oembed?url=<url>&format=json` →
  `title`, `author_name`, `thumbnail_url`. Keyless, no yt-dlp. Offline
  fallback: derive `hqdefault.jpg` from the video id even if oEmbed
  fails.
- Web: GET the page (browser User-Agent, timeout, size cap), parse head
  for `og:title` / `og:image` / `og:description`, falling back to
  `twitter:*` tags and `<title>`. stdlib parsing; no headless browser.

Runs:

- At enqueue for new items (`add_urls` and the reddit/web adapters call
  it inline; one small request per item).
- As a backfill inside the hub refresh cycle: newest-first over pending
  items with `hydrated_at is None`, small batch per cycle, throttled via
  the existing `last_pulls` bookkeeping. Every attempt stamps
  `hydrated_at`; failures also set `hydrate_error`.

Hydration fills only empty slots except `preview_url`, which it may
upgrade (Reddit postage-stamp thumb → real cover).

## Ingest routing

Reddit handler ingests the note natively (selftext + comments +
attachments). When an attachment link classifies as YouTube:

- If not already ingested (`db.is_processed`), run the native YouTube
  ingest for it as its own note.
- Cross-link both notes with wikilinks in each direction (feeds the #4
  wikilink gap).
- If already ingested, link without re-ingesting.

## Card and preview repair

- Title slot (`web/src/components/Card.tsx`): `title || excerpt(text)
  ||` explicit neutral state. Never `author`, never the URL.
- `CardMeta`: `author` as provenance; hostname suppressed when it
  restates the source label (`youtube · youtube.com` → `youtube`).
- `hub.cover_for`: log failures with item URL, delivery host, and
  exception class. When `preview_url` changes (hydration or IG
  rediscovery), invalidate the cached cover keyed by the item URL so
  the new URL is actually tried.
- IG rediscovery may overwrite a broken/stale `preview_url` while
  preserving all other row fields.

## Testing

- Real-shape fixtures: playlist row with `text=null`; Reddit row with
  gallery + external YouTube link.
- Flip the two tests that encode the bug: `tests/test_source_refresh.py`
  (title-in-author assertion) and `web/src/lib/provenance.test.ts`
  (`youtube.com` label expectation).
- Hydrator: fake fetcher covering oEmbed success, og fallback chain,
  permanent failure marking, fill-only-empty semantics.
- Cover cache: unusable host logs and returns None; preview_url change
  invalidates and recovers.
- Card: combined rendered output for real-shape rows (no duplicate
  title, neutral state, no hostname echo).
- Retrieval eval gate untouched — nothing here reaches `store.py`.

## Out of scope

- Instagram caption capture (stays open under #163).
- Generic-web crawling beyond og/head parsing.
- Cover dimensions in the queue API (#131).
