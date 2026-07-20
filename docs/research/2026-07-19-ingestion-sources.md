# Ingestion source survey — TikTok, HN, X, Reddit, Spotify

Date: 2026-07-19. Produced by a 6-agent research workflow (5 per-source surveys with
live web verification, 1 synthesis). All API/pricing facts checked against current
2026 sources; citations inline per section.

## Verdict at a glance

| Rank | Source | Verdict | Effort | Why |
|---|---|---|---|---|
| 1 | TikTok | build now | ~0.5 day | Ingest path already exists (`add-tiktok`); only an export parser is new. Zero ban risk. |
| 2 | Hacker News | build now | ~1 day | Public favorites page + free unauthenticated Algolia API, both verified live. No auth at all. |
| 3 | X bookmarks | build soon | 2–3 days | Official API now pay-per-use (~$0.001/read, dollars/year). Build the ingest half first. |
| 4 | Reddit saved | build soon | 1–2 days + waiting | Self-service OAuth died Nov 2025; hinges on grandfathered credentials. Do the admin moves now. |
| 5 | Spotify | skip for now | ~1 week | Premium-gated Dev Mode, 1 Client ID per developer, unmeasured RSS coverage. Revisit if the maybe hardens. |

## Phase 0 — admin day (zero code, do immediately)

Everything below overlaps multi-day waits, so fire these off before writing any code:

1. **Request the TikTok data export** (Settings → Download your data → **JSON**, Select all). 1–4 day turnaround.
2. **File the Reddit GDPR data request** at reddit.com/settings/data-request (up to 30 days).
3. **Check reddit.com/prefs/apps** for any pre-Nov-2025 OAuth app — grandfathered credentials collapse the whole Reddit decision tree. If none, submit a Responsible Builder application (free option value, uncertain approval).
4. **Decide the HN save gesture**: favorites are public and scrapable without auth; upvoted is private (login-cookie only, robots-disallowed). Adopting "favorite" as the save gesture makes HN a zero-credential source.

## TikTok (rank 1 — the definite want)

**Bottom line:** the backlog is fully recoverable, but not live. There is NO programmatic
path to private favorites — yt-dlp can't enumerate them (issue #1584 open since 2021),
TikTokApi supports no user-authenticated routes, the Display API only covers your own
posted videos, and the Research API is academics-only. What works:

- **Official data export (backlog)**: `user_data_tiktok.json` → `["Likes and Favorites"]["Favorite Videos"]["FavoriteVideoList"]`, each entry `{Date, Link}` with tiktokv.com share URLs that yt-dlp resolves. Also Like List and Watch History. Must pick JSON (TXT is truncated). Free, zero risk, snapshot-only.
- **Go-forward**: share-to-self via iMessage — rides the existing phase-7 iMessage capture with zero scraping. Verify the capture regex routes vm.tiktok.com / www.tiktok.com to `source="tiktok"`.
- **Top-ups**: dinoosauro/tiktok-to-ytdlp browser console script (maintained, Jan 2026) scrolls your logged-in Favorites page and emits a URL list. Lowest-risk scraping shape that exists.

**ytk fit:** new discovery only — `ytk tiktok-import <file>` parsing the export (accept
both `Link`/`link` casings and plain TXT/JSON URL lists), normalize, dedupe by video id,
drain into the pending queue. Ingestion is unchanged `add-tiktok`. Expect dead links in
an old backlog — log failures, don't hard-error. Check photo-mode (slideshow) posts
against the Instagram-slides image path.

**Open questions:** export size cap on thousands of saves (verify on the real export);
short-link (vm.tiktok.com) expiry — resolve to canonical URLs at capture time?

## Hacker News (rank 2 — easiest true source)

**Verified live 2026-07-19:** `/favorites?id=USER` is public, 30/page, stable
`athing` markup, `&comments=t` tab for favorited comments. `/upvoted` is private
(login form). Anonymous traffic is aggressively rate-limited — ~4 quick requests earned
a multi-minute 429 block; robots.txt says `Crawl-delay: 30` and does not disallow
/favorites. Algolia API (`hn.algolia.com/api/v1/items/{id}`) returns the story plus the
entire nested comment tree in one free unauthenticated request; Firebase API as fallback.

**ytk fit:** `ytk/hn.py` fetcher modeled on reels.py — daily sync, browser UA, 30s
between pages, exponential backoff on 429, stop at first already-seen id (favorites are
newest-first, so incremental sync is usually 1 request). Ingest: linked article through
the existing trafilatura path untouched; new code is only `hn_comments(story_id)` via
Algolia and a note-composition tweak appending `## HN Commentary` (top ~5 top-level
comments + best reply, char-capped) before enrichment. Notes land in
`second-brain/sources/hackernews/`.

**Dead ends evaluated:** bsandrow/hn-saved-stories (dead since 2013), dogsheep
hacker-news-to-sqlite (no favorites support). ~60 lines of requests + stdlib beats both.

## X bookmarks (rank 3 — cheap now, volatile pricing)

**The 2026 pricing flip:** tiered pricing died Feb 2026; "Owned Reads" (your own
bookmarks/likes/timeline) cost **$0.001 per resource** as of April 2026 — a monthly
200-bookmark sync is ~$0.20. No free tier; credits bought upfront. OAuth 2.0 PKCE with
`bookmark.read`. The API historically returns only the most recent ~800 bookmarks.
The official data archive does NOT include bookmarks (still true April 2026).

- **Backfill:** twitter-web-exporter userscript (maintained, v1.4.0 Feb 2026, works in Zen via Violentmonkey) passively captures the GraphQL responses of your own scrolling — beats the 800-item window, free.
- **Hydration without X auth:** `api.fxtwitter.com/status/:id` — full tweet JSON, threads, media, no auth, 1000 req/min. vxtwitter and the syndication endpoint as fallbacks. Nitter is dead as a public service.
- **Do NOT** use twscrape for bookmarks: it forces real-account cookies into a scraper on a platform actively banning scraper sessions, to save ~$2/year.

**ytk fit:** build the **ingest half first** (~1 day): fxtwitter hydration + dispatch —
long text → Haiku; `entities.urls` → trafilatura; video tweets → yt-dlp + whisper
(x.com is a supported yt-dlp extractor); images → vision path. Pasted x.com URLs then
work in the inbox with zero X auth. Discovery half later (~1–2 days, mostly OAuth and
console signup friction). Re-verify the $0.001 rate and minimum credit purchase at
signup — X changed pricing three times in 18 months.

## Reddit saved (rank 4 — bureaucratically gated)

**The landscape hardened:** self-service OAuth app creation ended Nov 2025 (Responsible
Builder Policy — manual application, ~1–4 weeks, uncertain approval for personal
scripts). Pre-Nov-2025 credentials are grandfathered and keep working (PRAW
`user.me().saved(limit=None)`, free non-commercial ~100 QPM). Unauthenticated `.json`
endpoints were 403'd May 2026, but **logged-in session-cookie** requests to
`old.reddit.com/user/<name>/saved.json` still work — same gray zone as the existing
instagrapi fetcher. All live listings cap at ~1000 saves; the GDPR export
(saved_posts.csv, id+permalink only) is the only historical backfill and needs
hydration afterward.

**ytk fit:** transport-agnostic poller (PRAW if credentials exist, else cookie) →
type dispatcher: selftext → Haiku directly; link post → trafilatura on the target;
v.redd.it → yt-dlp + whisper; galleries → vision. Top-comments formatter shared with
HN. Track seen-ids locally rather than unsave-on-ingest (write scope not worth it).

## Spotify (rank 5 — skip until the maybe hardens)

The API path survived the Feb 2026 lockdown — `/me/tracks`, `/me/shows`, `/me/episodes`,
playlists all still work in Dev Mode via spotipy ≥ 2.26.0 — but three hard gates:
Dev Mode now **requires an active Premium subscription** (integration dies if it
lapses), exactly **1 Client ID per developer**, and podcast audio is DRM'd so
transcription requires RSS-matching (iTunes Search / Podcast Index) + enclosure
download + whisper, with an unmeasured Spotify-exclusive dead zone. Music-track notes
are thin for a knowledge vault — better as interest-model signal than per-track notes.
If revisited: run the one-hour RSS coverage probe against actually-saved shows first.
Avoid Musixmatch (storage prohibited) and all sp_dc-cookie scraping (active crackdown).

## Shared abstractions (build once, not five times)

1. **Discovery-fetcher protocol**: `fetch(state, config) -> list[ReelItem]` registered in `hub.refresh_sources()` (failure isolation + cadence throttling already exist); per-source cursors as `cursors: dict[source, str]` in ReelsState; dedupe via `hub.ingested_urls()`.
2. **`classify_url()`** stays the single URL→source router — add news.ycombinator.com, x.com/twitter.com, reddit.com/redd.it once; paste-to-queue, iMessage, and fetchers all classify identically.
3. **Ingest dispatch registry**: extract the source→handler mapping out of if/elif arms; add-x/add-reddit/add-hn become thin entries routing to existing machinery.
4. **`ytk import <file>`**: one export-importer shape shared by the TikTok export JSON/TXT, twitter-web-exporter dumps, and Reddit GDPR CSVs.
5. **Commentary appender**: HN and Reddit share one top-N-comments formatter (`## Commentary`, score/author, char-capped, prepended to enrichment input).
6. **Vault**: each source gets `second-brain/sources/{slug}/` with typed asset subfolders, globally unique basenames.

## Risks

- TikTok export is snapshot-only; go-forward depends on share-to-self habit; dead-link rate in old backlogs needs a failure ledger.
- X pricing volatility; ~800-bookmark API window makes the browser backfill mandatory.
- Reddit approval odds uncertain; cookie fallback breakable every few weeks.
- HN 429s are real at trivial burst rates — the 30s crawl-delay is load-bearing.
- New note shapes (comment-heavy, threads) change the embedding corpus — the frozen retrieval eval gate (`uv run ytk eval`) must pass before any store-visible change.
- Ingest-dispatch refactor touches hub.py while the daemon runs — reinstall does not restart it (`launchctl kickstart -k gui/501/com.ytk.hub`, check /api/ingest/status first).
- Queue flooding: a multi-thousand-item TikTok drain could bury the inbox picker — importers need batching.

## Phased plan

- **Phase 0** — admin day (above), today.
- **Phase 1** — TikTok import (~0.5 day): parser + queue drain + iMessage routing check.
- **Phase 2** — HN (~1 day): favorites fetcher + Algolia commentary + note composition.
- **Phase 3** — X ingest half (~1 day): fxtwitter hydration + dispatch + backfill importer.
- **Phase 4** — X discovery (~1–2 days): developer signup, PKCE, bookmarks poller.
- **Phase 5** — Reddit (~1–2 days, contingent on Phase 0 findings).
- **Phase 6** — Spotify (deferred; gates first).

Each phase ends with the retrieval eval gate if store behavior was touched, a hub
restart after reinstall, and a session brief.

Full per-source survey JSON (access paths, citations, open questions):
`/private/tmp/claude-501/-Users-melocoton-Developer-ytk/dffe6bee-0225-4a2f-a42b-c23d6ea4f55b/tasks/wj24ci1sc.output`
