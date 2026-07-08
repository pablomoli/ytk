# Bundled Entries with Multi-Source Coherence

Date: 2026-07-07
Status: Draft for review (v4 — adds image atoms; sessionize keeps timer, drops merge)

## Problem

Two independent shortcomings in the iMessage self-note pipeline, plus one
pre-existing embedding issue they surface:

1. **Thoughts are flattened into one string.** A sitting's messages are joined
   before ingest. The join is built when the queue item is created —
   `refresh_sources` at hub.py:450 (`full = "\n\n".join(m.text for m in
   s.messages)`), and mirrored by `MessageThread.as_text()` (imessage.py:35-36).
   By the time `ingest_imessage_item` (hub.py:159) runs, `item.text` is already
   one blob — the individual thoughts are no longer addressable.

2. **Multiple sources are enriched blind.** A note carrying multiple links fans
   out `for u in urls: INGEST(u, steer)` (hub.py:172-180). Each link becomes its
   own `sources/` note with its own enrichment, but none of them knows the others
   exist, so related links share no context.

3. **(Pre-existing, separable) Long memories truncate.** `upsert_doc`
   (store.py:235-241) stores `text[:8000]` as a single vector; `gte-small`
   hard-truncates at ~512 tokens, silently dropping the tail. This is not caused
   by this feature but affects long self-note sittings today. Scoped as an
   optional, independently-shippable section below.

## Decision: group, don't merge

The coherence win comes from **linking** the per-source notes into one bundle and
feeding each source's enrichment its siblings as context — NOT from collapsing
them into a single note. This preserves every current behavior: per-source
`sources/` notes keep their own thumbnail, date, title, and independent
enrichment, and the fresh feed keeps showing one card per source with zero
changes to `fresh_notes` (hub.py:821). Merging into one note was rejected: a
single collapsed note has one thumbnail/date/mtime, so `fresh_notes` could not
rebuild the distinct per-source cards it shows today (it derives each card's
thumbnail/date from that note's own frontmatter and mtime, hub.py:844-862).

## Goals

- Every atom in a sitting — each thought, each link, each image — becomes its own
  note. Nothing is flattened or merged.
- Atoms in the same sitting are linked by a shared `bundle_id`, and each source's
  enrichment is steered by its siblings (prose + the other links).
- Image attachments (dropped today) are captured: own note, `image_paths`
  thumbnail, SigLIP-2 visual embedding.
- No regression to the fresh feed, dedup, thumbnails, or per-source enrichment.
- Optionally (separable): kill the 512-token memory truncation cliff.

## Non-Goals

- **No merged/collapsed note.** Sources stay as independent `sources/` notes.
- **No semantic pull-in.** "Alike" means *same sitting only*. No embedding-based
  matching against the wider vault. Deferred.
- No change to the `$$` marker, warm-session hold, or the `note_id` id scheme.
  Note: memo capture has a *second*, now-stronger dedup layer. As of commit
  `a32c212`, `write_memo_note` computes a transcript content hash and, via
  `_recent_memo_with_hash`, reuses an existing memo with the same hash written
  within a 6h window (`_DEDUP_WINDOW_SECONDS`) instead of writing a new file.
  This is independent of `note_id`. The N-notes path below interacts with this
  guard — see the carve-out in "Thoughts as an array."

## Design

### Bundle identity

Every note produced from one sitting carries `bundle_id: imessage:session:<digest>`
(the existing `Session.note_id`, imessage.py:176) in its frontmatter. This is the
only new stored field. It groups the per-source notes and the prose memo (if any)
as one logical entry without merging them. `bundle_id` is provenance metadata —
it is NOT written as a `url:` field, so `ingested_urls`/dedup (hub.py:276-294,
488) continue to key on real source URLs and nothing re-queues.

### Sibling-steered enrichment (the coherence win)

Today `ingest_imessage_item` already aggregates the sitting's prose into `steer`
and passes it to each `INGEST(u, steer)` (hub.py:172-180). Extend `steer` to also
name the sibling URLs in the same bundle, so each source's enrichment sees "this
was captured alongside <other links> and these notes." Single enrichment per
source is unchanged; it just gets richer context. One link in a sitting behaves
exactly as today (no siblings -> steer identical to current).

### Thoughts as an array (prose-only sittings)

For the prose-only path (no links), stop flattening the sitting into one memo
note. Carry `Session.messages` through as `texts: list[str]` and write **one memo
note per thought** (resolved fork, see below). Each thought stays individually
addressable, searchable, dedupable, and card-able — which is spec goal #1;
listing thoughts inside one note would re-flatten at presentation what we
un-flattened at ingest. The join site to change is the queue-item build at
hub.py:450 and the memo write at hub.py:182-193 — NOT the consumer, which already
receives whatever `item.text` holds.

**Dedup carve-out.** `write_memo_note`'s content-hash guard (commit `a32c212`)
would collapse two word-for-word-identical thoughts in the same sitting into one
card. Almost never happens, but to guarantee "N notes always," scope the dedup
hash to `(thought_text, thought_index)` — or pass an explicit per-thought id —
so identical thoughts at different positions in a sitting stay distinct, while
the cross-sitting re-send dedup the commit was built for still fires.

### Images as atoms (new capability)

Today image attachments are dropped: `read_recent` strips the `￼` placeholder
(imessage.py:142) and never looks at the attachment. Now each image becomes its
own note, sharing the sitting's `bundle_id` with any accompanying thought.

- **Read.** Extend `read_recent` to also pull attachment rows —
  `message_attachment_join` -> `attachment.filename` gives the on-disk path
  (attachments already live under `~/Library/Messages/Attachments/`, so this is a
  path read, not a blob decode). Filter to image MIME types. An image attachment
  becomes an atom alongside text atoms, carrying its source file path.
- **Save + note.** Copy the image into the vault (e.g.
  `sources/imessage/<bundle>-img-N.<ext>`), write a note with `image_paths:`
  frontmatter (so `fresh_notes` thumbnails it automatically, hub.py:844) and
  `bundle_id`. An optional light Claude-vision caption (`vision.image_blocks`,
  vision.py:122) gives the note body text for semantic search; the raw image is
  the artifact.
- **Visual embed.** Call `visual.embed_cover_for_save(image_path, item_id,
  metadata)` (visual.py:303) -> `store.upsert_visual`, so the image joins the
  SigLIP-2 index and shows up in visual/inbox similarity search like any other
  cover.
- A message carrying both text and an image yields **two** atoms (a thought note
  and an image note) sharing one `bundle_id`.

### Fresh feed

Unchanged. Because every atom (thought, link, image) stays an independent note,
`fresh_notes` needs no edits — text atoms render as memo cards, image atoms
thumbnail via `image_paths`, link atoms are `sources/` cards as today. A future
nicety (out of scope) could show a "bundled with" affordance by reading
`bundle_id`, but the feed works untouched.

## Optional, separable: memory truncation part-split

Independent of bundling; can ship on its own. Mirror the video part-split
(store.py:276-326) for long memory notes, but scope it carefully — `upsert_doc`
is the generic sink for EVERY vault note (vault.py:748 reindex, cli.py reindex
commands, mcp_server.py, snap.py screenshots, and the memo index path in
memo.py — note memo.py line numbers shifted down ~27 lines after commit
`a32c212`). Required coordinated
edits the first draft missed:

- Only part-split when the doc exceeds the token budget; short notes keep one
  vector (no behavior change for the common case).
- Part ids `#s1…#sN` must be filtered (`"#" in id -> continue`) in
  `get_content_memories` (store.py:569-600) — it currently has NO such filter,
  unlike `get_all_videos` (store.py:544) and `tag_counts` (store.py:524) — or
  synthesis clustering double-counts fragments.
- `search_all`'s memory branch (store.py:482-493) must switch to `n*3`
  over-fetch and add a memory analogue of `_collapse_by_video` that keys on
  `doc_id` (not `video_id`, which memories lack, store.py:381) and maps a part
  hit back to the representative doc for `excerpt`/`title`.

Recommendation: ship bundling first (goals 1-3), treat this as a follow-up PR.

## Testing

- One link in a sitting: output byte-identical to today (steer has no siblings).
- Two links in a sitting: both `sources/` notes carry the same `bundle_id`; each
  enrichment's steer names the other URL; two independent notes and two fresh
  cards as today (no collapse).
- Prose-only sitting: N thoughts -> N memo notes, same `bundle_id`, identical
  thoughts at different indices stay distinct (carve-out).
- Image attachment in a sitting: decoded from the attachment join, saved into the
  vault, its note carries `image_paths` + `bundle_id`, and a visual vector lands
  in the SigLIP index. A text+image message yields two atoms sharing a bundle.
- Dedup: re-pulling a link already ingested in a bundle is still recognized via
  its `url:` frontmatter; nothing re-queues (hub.py:488).
- Memory part-split (if included): a long note produces `#s*` parts; `search_all`
  collapses to one hit and the tail is retrievable; `get_content_memories` and
  `tag_counts` count the entry once.

## Resolved decisions

- **Bundle model:** group, don't merge. Every atom is its own note.
- **Sessionize:** stops merging a sitting into one node, but still runs to time
  the warm-hold flush and stamp the shared `bundle_id`.
- **Prose-only sitting with N thoughts:** N memo notes (one card per thought),
  with the dedup carve-out above so the `a32c212` guard doesn't collapse
  identical-but-distinct thoughts.
- **Images:** in scope — each attachment is its own note + visual embedding.
- **"Alike" scope:** same sitting only; no semantic pull-in.

Nothing is left open. Awaiting user sign-off to commit and move to a plan.
