# Handoff: YouTube description backfill + re-embed (issues #105, #106)

Self-contained brief. Written 2026-07-24. Agent-agnostic.

Long-running, IO-bound, safe to leave unattended — but it touches the
embedding space, so the retrieval eval gate is a **hard** stop-or-go, not a
formality. Read the "decision point" section before starting; the job has a
branch in it that a human may need to settle.

## What is actually missing (verified, not assumed)

- `ytk/metadata.py` **already fetches** the description — line 26,
  `"description": info.get("description", "")`. Nothing to build there.
- The description is **never persisted**: it does not reach the vault note
  (`ytk/vault.py` writes summary / concepts / moments / transcript, no
  description section) and it does not reach the embedded document.
- The embedded doc for a video is built in `ytk/store.py::upsert` from the
  **enrichment only** — `thesis + "\n\n" + summary` for the representative
  vector under the current v2 epoch.
- Scale: **153 videos** in `ytk_videos_v2`, 155 notes on disk under
  `second-brain/sources/youtube/`.

So this job is: fetch descriptions for 153 existing videos → persist them →
decide whether they enter the embedding → re-embed if so → prove retrieval
did not regress.

## Phase 1 — backfill descriptions (safe, additive, no embedding change)

Write `scripts/backfill_descriptions.py` following the conventions of the
existing backfill scripts (`scripts/backfill_capture_times.py`,
`scripts/backfill_ig_thumbs.py` — read one first for house style: dry-run
default, `--apply` to write, progress logging, resumable).

Requirements:

- **Dry-run by default.** `--apply` performs writes. Print a summary table
  of what would change before touching anything.
- **Resumable.** Keep a small JSON ledger (e.g. `~/.ytk/description-backfill.json`)
  of `video_id → fetched|failed|skipped`, so a re-run picks up where it
  stopped. This is the difference between a job that survives an
  interruption and one that starts over.
- **Rate limiting.** yt-dlp against 153 videos back to back invites
  throttling. Sleep ~1–2s between fetches, and back off on failure rather
  than hammering. Total runtime is expected in the tens of minutes; that is
  fine and is the point of running it unattended.
- **Failures are data, not exceptions.** Deleted/private videos will fail.
  Record them in the ledger, keep going, and print the list at the end.
- **Where the text goes:** append a `## Description` section to the video's
  vault note, placed **after `## Key Moments` and before `## Transcript`**
  (so the note's readable summary stays at the top). Wrap it in a
  `<details>` block like the transcript already is, since descriptions can
  be very long. Also persist the raw text where the pipeline can reach it
  without re-fetching — the video's Chroma metadata is the natural home
  (metadata is not embedded, so this is storage only, exactly as decided).
  Hashtags and chapter markers survive verbatim; do not strip them.
- **Idempotent.** A note that already has a `## Description` section is
  skipped, not duplicated. Same rule the "My take" append already follows
  in `store.py`.

Verify on a handful first: `--limit 5 --apply`, then read the notes.

## The decision, already made: store it, enrich with it, do NOT embed it

**Settled by the user 2026-07-24 — do not re-litigate, and do not add
description text to any embedded document.**

- **Store the raw description.** Descriptions carry real signal the
  transcript misses — tags, hashtags, chapter markers, tool names, links —
  alongside sponsor boilerplate. Keeping the raw text costs nothing and
  makes every future use (a `#d` part, a keyword index, a tags extractor)
  possible without re-fetching 153 videos.
- **Feed it to enrichment.** Haiku sees description + transcript, so the
  thesis, key concepts and moments can pick up what the transcript missed.
  The embedded doc stays `thesis + summary` — the exact shape the retrieval
  gate was measured on, just with better content in it.
- **Never into the embedded doc.** The comment in `store.py::upsert` is
  explicit that folding extra material into the representative doc is
  "unmeasured (spec Phase 3)", and raw descriptions are noisy enough to
  plausibly dilute a clean signal. Not this job.

That last rule is what makes this job safe to run unattended: the only way
the vector space changes is via *better enrichment text*, which the gate
below still checks, but there is no experimental embedding design in flight.

If, while working, the case for a `#d` embedded part starts to look
compelling — write it up, leave it unimplemented, and let the user decide.
Do not ship it in this pass.

## Phase 2 — re-enrich / re-embed

Re-enrichment costs Haiku calls for 153 videos. Budget accordingly and make
it resumable in the same way as Phase 1.

Order of operations matters:

1. Confirm `/api/ingest/status` shows `"running": false` before starting.
   The hub writes to the same Chroma store; a concurrent ingest during a
   bulk re-embed is asking for trouble.
2. **Snapshot the store first.** `~/.ytk/chroma` — copy the directory. This
   is the rollback path, and there is no other one.
3. Record the current baseline: `uv run ytk eval` (156 frozen known-item
   queries, `eval/retrieval/queries.jsonl`, baseline in
   `eval/retrieval/baseline.json`).
4. Re-enrich + re-upsert. Existing tooling to read before writing new:
   `experiments/migrate_embedder.py` (bulk re-embed patterns),
   `scripts/rebuild_video_parts.py` (part rebuild).
5. Re-run `uv run ytk eval` and compare.

## The gate — non-negotiable

`uv run ytk eval` scores the frozen 156-query set through the production
search paths and **fails on regression** against
`eval/retrieval/baseline.json`. Rules:

- If hit@1 regresses: **do not** `--update-baseline`. Roll back to the
  Chroma snapshot and report the numbers. A regression is a finding worth
  more than the feature.
- If it improves or is flat: re-stamp with `--update-baseline` and note the
  epoch + date in the commit message (the baseline file carries both).
- Either way, write the before/after numbers into the PR body. "Passed" is
  not a number.
- Live end-to-end check: `uv run pytest -m eval`.

## Downstream consequences (do not skip)

If the embedding changed at all, everything derived from it is stale:

```bash
uv run python scripts/build_map.py --sweep     # refit UMAP params, rebuild map
uv run --with matplotlib python scripts/plot_assets.py --refresh   # all 9 figures
```

And per `docs/assets/fog/linkedin-notes.md`: **keep the pre-change PNGs.**
The before/after pair — same map under old vs new embeddings — is itself
report material. Every number quoted in that notes file (median 0.55h,
98.8% within 2h, 10 strands, 5 junctions) must be re-read from the new run,
never copied forward.

Note the sequencing with #106 (semantic domains): #106 only re-*colours*
(positions are already semantic; only the labels are path-derived), while
this job re-*shapes*. If both are to land, do this one first, then #106, so
the layout reshuffles exactly once.

## Acceptance

- Backfill script: dry-run default, `--apply`, `--limit`, resumable ledger,
  rate-limited, idempotent, failures listed at the end.
- 153 videos attempted; per-video outcome recorded; failures explained.
- Notes carry `## Description` in the right position, no duplicates.
- Store snapshot taken before any re-embed.
- `uv run ytk eval` before/after numbers in the PR body; baseline re-stamped
  only on improvement or parity.
- `uv run --extra dev pytest -q` green.
- If re-embedded: map rebuilt, figures regenerated, old PNGs preserved.

## Gotchas

- **Never restart the hub mid-job.** Inspect `/api/ingest/status` output as
  its own command, decide, *then* act. Chaining a status check and a
  `launchctl kickstart` with `;` or `&&` restarts unconditionally — that
  has already cost one interrupted batch.
- **The Bash cwd drifts** after `cd web && ...`; `uv run python scripts/...`
  then fails *silently*. Prefix every command with
  `cd /Users/melocoton/Developer/ytk && `.
- **Deploy from a clean export**, never from a dirty working tree:
  `git archive HEAD | tar -x -C <tmpdir>` then
  `uv tool install --reinstall <tmpdir>`.
- Use the **`wt` CLI** for worktrees, never `git worktree`.
- yt-dlp breaks periodically against YouTube changes. If fetches fail
  wholesale rather than individually, check the yt-dlp version before
  assuming the script is wrong.
