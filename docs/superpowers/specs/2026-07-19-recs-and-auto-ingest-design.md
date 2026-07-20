# Recommendation surfaces + profile-matched auto-ingest — design

Date: 2026-07-19. Status: forks resolved in session; awaiting spec review before
implementation. Builds on the interest profile (`me/profile.md`), the enrichment
pipeline, ChromaDB store, and the hub.

Three surfaces, two of which share one machine:
1. Watch recommendations surface — movies, live-action shows, anime
2. Read recommendations surface — books, manga
3. Profile-matched auto-ingest of pending items

Recommendation kinds: `movie`, `show`, `anime`, `book`, `manga`. Anime and manga
are first-class (not folded into show/book) — the user watches/reads both and
anime is one of their profile themes.

## Decisions (locked)

| Fork | Decision |
|---|---|
| Rec kinds | movie, show, anime, book, manga. |
| Rec detection | Tag-driven, automatic. Enrichment applies a `{kind}-rec` tag (coexisting with the note's other tags) when it detects one, and extracts the structured title/creator. Inbox chip is an optional manual override applying the same tag. |
| Backfill | Yes — one extraction pass over existing ~280 notes, then continuous going forward. |
| Metadata sources | movie/show: TMDb (free key `TMDB_API_KEY`). anime/manga: AniList (free, no key). book: Open Library (free, no key). |
| Auto-ingest selection | Stratified by interest theme (best match within each theme, slots spread across themes). |
| Auto-ingest cadence | Weekly, 30 items, hard-capped, launchd. Configurable. |

## Surfaces 1 & 2 — Watch (movie/show/anime) / Read (book/manga)

### Detect (in enrichment)
Extend the `Enrichment` schema with `recommendations: list[Recommendation]`,
`Recommendation = {kind: "movie"|"show"|"anime"|"book"|"manga", title, creator: str|None, reason: str|None}`,
empty when the note recommends nothing. When non-empty, enrichment also appends
the matching `{kind}-rec` tag(s) to `interest_tags`, alongside the content tags.
The prompt instructs: extract specific titles recommended OR substantively
discussed, with the recommender's reason if stated, and distinguish anime from
live-action show and manga from book.

Membership in a surface = note carries a `*-rec` tag. The structured
`recommendations` entries carry the titles to resolve. The inbox already supports
tag chips; `{kind}-rec` chips are a manual override that forces the tag when the
AI misses one.

### Resolve + dedupe (free APIs)
`ytk/recs.py`, one resolver per kind, dispatched by `Recommendation.kind`:
- `resolve_movie(title, creator, year)` — TMDb `/search/movie` (poster, release
  year, director via credits, vote_average, overview, tmdb_id). Key required.
- `resolve_show(title, year)` — TMDb `/search/tv` (poster, first_air_date,
  overview, vote_average). Key required.
- `resolve_anime(title)` — AniList GraphQL `Media(type: ANIME)` (coverImage,
  seasonYear, averageScore, studio, romaji/english title, id). No key.
- `resolve_manga(title, creator)` — AniList GraphQL `Media(type: MANGA)`
  (coverImage, startDate, averageScore, staff, id). No key.
- `resolve_book(title, creator)` — Open Library `/search.json` (cover_i,
  author_name, first_publish_year, isbn, subjects). No key.
- Canonical key: `tmdb:{id}` / `anilist:{id}` / `isbn:{isbn}` (fallback
  `kind|title|creator` slug when unresolved). Dedupe merges provenance and bumps
  a per-entry count.
- Cache posters/covers to `sources/recs/{kind}/covers/` (typed subfolder,
  globally unique basenames — vault-assets-never-flat).

### Store
`~/.ytk/recs.json`: `{ canonical_key: { kind, title, year, creator, metadata{poster,
overview, rating, url}, sources: [note_path...], count, first_seen, status:
"want"|"seen"|"skip" } }`. Rebuildable from the vault by re-scanning `*-rec` tags,
so it is a cache, not a source of truth. Optional mirror to a vault index note.

### Surface (hub)
`/recs` page grouped into **Watch** (movie/show/anime) and **Read** (book/manga),
with per-kind filter chips. Poster/cover grid; each card: title, year, creator,
rating, "recommended in N notes" linking back to source notes, and a
want/seen/skip toggle. Sortable by count (default), recency, rating. New React
route `web/src/routes/recs.tsx` + `GET /api/recs?kind=movie|show|anime|book|manga`
and `POST /api/recs/{key}/status`.

### Backfill
`ytk recs-backfill` — iterate existing notes, run the recommendation extractor
over each (Haiku), apply tags, resolve, populate `recs.json`. Idempotent; skips
notes already scanned (tracked by a scanned-set).

## Surface 3 — Profile-matched auto-ingest

### Score
`ytk/autoingest.py`: embed each pending item's text (caption/title/desc) with the
production encoder; score against the interest-profile theme centroids (from the
latest profile snapshot), weighted by theme weight. Items with too little text
fall back to a low score.

### Select (stratified by theme)
Assign each pending item to its best-matching theme, then allocate the batch (30)
across themes — proportional to theme weight with a floor so small themes still
get a slot — and take the top-scoring items within each theme. Diversity plus
relevance; avoids the dominant theme (3D/VFX, 25%) monopolizing every run.

### Ingest (small, debounced)
- launchd job (reuse `ytk schedule`), default **weekly**, `autoingest_count: 30`,
  hard cap enforced regardless of config.
- Runs new items through the existing ingest pipeline; existing duration/caption
  filters still apply.
- Auto-ingested notes tagged `auto-ingested`; each run logs its picks + the
  theme/score rationale to the daily digest.
- Config: `autoingest_enabled`, `autoingest_count`, `autoingest_cadence`.

## Sequencing (independently shippable)
1. **Recommendation extraction** — schema field + tags + prompt. Do first so
   auto-ingested notes also populate the lists.
2. **Recs resolve + store + backfill** — `ytk/recs.py`, TMDb/Open Library, backfill.
3. **Recs hub surface** — `/recs` page + API.
4. **Auto-ingest** — scorer, stratified selector, launchd job.

## Non-goals / risks
- Not building a full watch/read tracker beyond want/seen/skip.
- TMDb/Open Library title matching is fuzzy; keep an unresolved bucket rather than
  guessing, and let the user correct a mismatch.
- Enrichment schema change affects every future note and the eval corpus — the
  frozen retrieval eval gate (`uv run ytk eval`) must pass before shipping tag
  changes that touch the store.
- Auto-ingest bypasses human triage; the `auto-ingested` tag + digest log keep it
  auditable, and the weekly/30 cap bounds whisper cost and queue churn.
- Backfill Haiku cost is bounded (~280 notes, one cheap call each).
