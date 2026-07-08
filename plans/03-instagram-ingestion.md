# [plan-03] Instagram Ingestion Broken End-to-End — images unread, unembedded, unindexed

## Defect

The Instagram/reels ingestion path produces structurally incomplete notes at every
stage. It is not three bugs; it is one broken path with three visible symptoms:

1. **Read** — only the HTML text layer (caption/hashtags/counts) is fetched. Carousel
   slide images, the primary content, are never retrieved or OCR'd, causing partial or
   hallucinated ingestion.
2. **Write** — of 45 Instagram notes, only 4 embed any image, yet `sources/instagram/`
   holds 85 jpgs. 80+ images are orphaned and unreachable from their notes.
3. **Index** — Instagram points in `map.json` carry `u=''` and titles like
   `![[DY9uPRnoXdr-thumb.jpg]]`, so map labels are junk and URL matching is impossible.

## Children

- #35 — Instagram notes don't embed their images; 80+ orphaned jpgs (master)
- #3 — slide images not fetched, only HTML text layer read
- #39 — Instagram points in map.json have empty urls and image-embed titles

## Fix sequence

1. **Read**: add a Playwright (or existing scraper) image-extraction step for carousel
   slides; run each through `vision.py` for description + OCR before storing. If images
   genuinely can't be fetched, emit an explicit "slides unread" warning rather than
   silently ingesting text only.
2. **Write**: locate where the Instagram/reels note builder drops the embed; write one
   `![[{shortcode}-img-N.jpg]]` per fetched slide. Backfill existing notes by matching
   orphaned jpgs to their note by shortcode.
3. **Index**: ensure the store/index layer stamps the canonical Instagram URL and a
   human title (author + caption head) instead of the raw embed string, so map points
   and search results are usable.
4. Test: a fixture carousel asserts slides fetched, embeds written, and index metadata
   populated (non-empty `u`, human title).

## Test matrix

| Symptom | Assertion |
|---|---|
| Read | carousel with N slides -> N images fetched + N OCR descriptions |
| Write | ingested note contains N `![[...]]` embeds; 0 orphaned jpgs for that shortcode |
| Index | map/search entry has non-empty canonical URL and a human title |

## Out of scope

- Screenshot-sidecar empty-frontmatter theme noted in #35 — related orphaned-attachment
  hygiene, fold into the vault-hygiene track if it persists after this fix.

## Dependency

Share the fixed image-atom note builder + indexing path with **plan-02** (iMessage
photos) so image metadata is correct once, everywhere.
