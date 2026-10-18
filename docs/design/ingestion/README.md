# Ingestion: two layers, and what blocks the second

Plan of record, 2026-10-18. The fetch layer (layer one) is built and
described in `docs/architecture/fetch-layer.md`. This file is the plan for
layer two: what the ledger says slows it, what to change, in what order,
and which calls are the owner's.

## The measured picture (ledger, 2026-10-18)

| | value |
|---|---|
| capture to read (evidence on disk) | median 0 min, worst 13 min |
| capture to first enrichment | median 35 min, mean 20 h, worst 5.6 days |
| capture to kept | median 6.3 h |
| enrich + grade rounds per enriched item | 3.8 (137 enrich, 133 grade, 36 items) |
| model time per item | about 6.3 min (enrich 43 s, grade 58 s per round) |
| tokens per item | about 26.6k |
| owner captures since 2026-09-15 | 7 |

Asks since 2026-08-31, by kind:

| kind | raised | answered |
|---|---|---|
| grader bounce, twice | 57 | 50 |
| intent missing ("why this one?") | 49 | 20 |
| connections | 21 | 21 |
| transcript junk | 3 | 2 |
| budget spent | 1 | 1 |

Every enriched item (36 of 36) hit at least one grader bounce ask. The most
common answer in the ledger is "say what is wrong" (33). Of 30 landed
items, 12 landed because the grader passed a draft and 18 because the owner
chose "accept as is" over the grader.

Two nags, then, and the grader is the larger one. The intent ask is the one
that blocks a capture before any model runs.

## Done (branch feat/fetch-layer)

- Layer one: `fetch_url`, `fetch_frames`, `ytk add` showing the fetch.
- Layer two reads layer one's cache: no second download, same bytes.
- Transcript fixes on the curator path: `/shorts/` and `/live/` ids; manual
  `en-US`/`en-GB` tracks no longer fall through to Whisper.
- yt-dlp locked at the version the installed tool already runs.

## Step 3: the intent ask for deliberate captures

### What the ask does today

- `read_item` raises it whenever quality passes and the item has no take;
  `next_advanceable` picks a `read` item only when a take exists, so
  enrichment waits on it.
- It is the only ask that expires on its own: to `dropped` after 7 days,
  clock started at `asks.created_at`.
- Its filtering is silence, not judgment. All 25 drops ever came from the
  window expiring; "drop" was chosen 0 times. 12 of the 25 were never
  presented (the last `presented_at` in the outbox is 2026-09-30). One of
  them was a deliberate `ytk add` (item 806).
- On owner captures it fired 5 times and produced one sentence in the
  owner's voice. 15 of 21 owner captures already carried a reason from
  `--note` or the hub thought box.
- Whether a take improves enrichment is not shown: 10% grader pass without
  text against 15% with, confounded by source (all takeless items are
  YouTube) and underpowered.

### The design: deliberate surfaces imply a reflex take

The spec already holds this shape. `curator-engine.md`, the `$$` decision:
"The marker becomes capture plus a take of kind reflex (message text as the
take when present): the intent ask never fires, but the item still passes
read, grade and connect." It was never implemented.

1. `capture(..., silent_is_reflex: bool)`, passed explicitly by each call
   site. True from `ytk add` and the per-source adds, the hub Add box and
   queue picks, and `$$` auto-ingest. False from playlist sync, `feed` and
   `reels --all`. Keyed on the call site, never on the actor: the actor
   defaults to "owner" for `feed` and `reels --all` too.
2. A silent capture from a deliberate surface inserts a take
   `kind='reflex', text=''`. Nothing else in the state machine changes:
   `raise_intent_ask` is already a no-op with a take, the selector already
   picks read-with-take, and every take consumer (attempt header, enricher
   field guide, deterministic grader, rubric, note writer, connect, packet
   page) already handles empty reflex, because 10 sync items answered
   "just want it" and took that path.
3. The quality gate, the grader, the bounce ask and connections all still
   run.
4. No implicit take on a duplicate capture.

Two adjacent fixes the data argues for, one commit each:

5. An owner duplicate capture of an item with an open intent ask records an
   answer to it ("intent" with the note, "just want it" without), so the
   loop applies it. Today a note added that way never unblocks the item and
   the sweep still drops it.
6. The 7-day window starts at `presented_at`; an ask never presented never
   expires.

Rejected: a non-blocking ask (raised, but the loop advances anyway). It
breaks the one-open-ask invariant (`asks.py:73`: grader, budget and
connections asks would silently not raise), needs the selector and
`advance_item` loosened together (or the stuck rule parks the item after
about 45 min), needs a consumer for answers that arrive after landing (up
to 8 more model calls each), and leaves the CLI's `ask list` and the hub
digest disagreeing. All for about one owner sentence per five asks.

### Owner decisions before building

- Is the YouTube playlist deliberate? It is filled by hand on the phone,
  it is 38 of 59 captures, and it is the only place the ask removed
  anything (by expiry).
- Is an interactive `ytk reels` pick deliberate? (Same logic as a hub
  pick; never used.)
- The spec brief says "every item gets a sentence from the owner before
  enrichment". Step 3 amends it to "every item the owner did not choose
  gets one; a deliberate capture is the sentence". Say yes to the
  amendment, or keep the brief.
- Under step 3 an agent running `ytk add` without `--note` flows in with
  no reason. Today agents answer the ask within seconds anyway (3 of 3), so
  the outcome is the same.

### Tests that pin it

- cli capture without a note: one reflex take with empty text, surface cli;
  `read_item` returns no ask, state `read`; the tick routes it to advance.
- hub `ingest_via_cli(url, "")` and a bare `$$` link: the same.
- sync, `feed` and `reels --all` without a note: no take, intent ask raised
  (the existing `test_clean_read_without_take_raises_intent_ask` stays green).
- cli with `--note`: an intent take with the text (existing).
- duplicate silent owner capture of a kept item: no new take.
- duplicate owner capture with an open intent ask: an answers row, next
  tick `answered`, the sweep never expires it.
- `retry_parked` on an owner item with a reflex take: back to `read`, no
  intent ask.
- quality gate still first: an owner capture with a junk transcript gets
  "transcript junk", not skipped.
- expiry: an ask with `presented_at` NULL never expires; one presented 8
  days ago does.

### How to know it held (after shipping)

```sql
-- deliberate surfaces raise no intent asks; passive ones one per capture
SELECT i.provenance, count(DISTINCT i.id) captured,
       count(a.id) FILTER (WHERE a.kind = 'intent missing') intent_asks
FROM items i LEFT JOIN asks a ON a.item_id = i.id
WHERE i.captured_at >= :ship GROUP BY 1;

-- no new stuck parks (selector and verb disagreeing would show here)
SELECT count(*) FROM activity WHERE reason = 'stuck' AND at >= :ship;

-- nothing expires unseen, nothing with a take expires
SELECT a.item_id FROM activity a
JOIN asks k ON k.item_id = a.item_id AND k.kind = 'intent missing'
LEFT JOIN outbox o ON o.ask_id = k.id
WHERE a.action = 'expire' AND a.at >= :ship
  AND (o.presented_at IS NULL OR EXISTS (SELECT 1 FROM takes t WHERE t.item_id = a.item_id));
```

Expected: `cli` and `hub` rows with zero intent asks, zero stuck parks, no
rows from the third query.

Step 3 alone unblocks none of the six owner items stuck today: all six sit
on "grader bounce, twice" or "transcript junk".

## Step 4: the grader, the larger nag

Every enriched item is bounced at least once and 18 of 30 landings were the
owner overruling the grader. Each round costs about 100 s of model time.

Options, not yet chosen:

- **Land after one enrichment; the grader becomes an audit.** The draft
  lands; the grader's findings attach to the note as annotations and to
  the packet page, and only a deterministic failure (an ungrounded
  timestamp, a missing transcript) holds the item. Capture to kept becomes
  capture plus about 2 min. The cost: notes land with flaws the grader
  would have caught, said on the note instead of fixed.
- **Cap at one bounce round, then land with the findings.** Halves the
  rounds, keeps one correction pass.
- **Calibrate before changing anything.** The owner's 18 "accept as is"
  and 33 "say what is wrong" answers are labelled judgments of the
  grader's verdicts. Before moving it off the path, score how often the
  grader's bounce reasons match what the owner then said was wrong. If
  most bounces are rubric pedantry the owner overrides (the tag-with-a-
  question-mark bounce is one), the audit option loses little.

Recommendation: calibrate first (no model calls; the answers and grade rows
are in the ledger), then decide between audit and one round on the number.

## Step 5: smaller follow-ups

- The hub Add box shows the fetch the way `ytk add` does (the owner works
  from the hub; layer one is CLI and MCP only today).
- The curator's `gather_youtube` still makes a model call (`hint_detect`)
  and no sheet. Converge it onto the fetch path once the fetch has run in
  daily use for a while.
- `ytk gc` learns to prune `evidence/fetch/` (kept videos, storyboards,
  close-ups), never an entry a ledger bundle points into.
- Instagram image carousels through the fetch layer.
- Measure a larger or MLX Whisper against base int8 on ten reels before
  changing the model.

## Order

1. Merge the fetch layer (owner's go).
2. Step 3, after the four decisions above: one change plus two fixes, each
   with its tests.
3. Step 4 calibration, then the grader decision.
4. Step 5 as daily use asks for it.
