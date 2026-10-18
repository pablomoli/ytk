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
- Instagram image posts and carousels through the fetch layer.
- Step 3 (below).

## Step 3: a deliberate capture is the sentence (built 2026-10-18)

### What the ask did before

- `read_item` raised it whenever quality passed and the item had no take;
  `next_advanceable` picks a `read` item only when a take exists, so
  enrichment waited on it.
- It is the only ask that expires on its own: to `dropped` after 7 days,
  the clock started at `asks.created_at`.
- Its filtering was silence, not judgment. All 25 drops came from the
  window expiring; "drop" was chosen 0 times. 12 of the 25 were never
  presented (the last `presented_at` in the outbox is 2026-09-30). One was
  a deliberate `ytk add` (item 806).
- On owner captures it fired 5 times and produced one sentence in the
  owner's voice. 15 of 21 owner captures already carried a reason from
  `--note` or the hub thought box.

### What runs now

The call site says whether the owner chose the URL (`capture(...,
deliberate=)`), never the actor.

| surface | deliberate | silent capture gets |
|---|---|---|
| `ytk add`, `add-tiktok`, `add-instagram`, `add-reddit`, `add-pinterest`, `ingest` | yes | reflex take, empty text |
| hub queue pick, `$$` auto-ingest, iMessage link sessions | yes | reflex take, empty text |
| interactive `ytk reels` pick | yes | reflex take, empty text |
| playlist sync, `feed`, `reels --all` | no | no take: the intent ask, as before |
| any CLI capture from an agent shell (`CLAUDECODE` or `AI_AGENT` set) | no | no take: the intent ask; with `--note`, an intent take whose surface is `agent` |

A note always becomes an intent take, as before. Downstream nothing
changed: the read gate (transcript junk, blind item), the deterministic and
model grader, the bounce ask and connections run on every item.

A deliberate capture of an item that already exists:

| item is | result |
|---|---|
| `dropped` | revived: take written, activity `revive` (actor owner) to `captured`; read, gate, grade and connect run again |
| waiting on an open "intent missing" ask | the ask is answered (`intent` with the note, `just want it` without); the loop applies it |
| before enrichment with no take | the missing take is written |
| anything else (kept, enriched, asking on a quality ask) | the note attaches as before; no reflex take, never a second note |

A passive re-capture never revives or answers. An agent capture is never
deliberate, so an agent can neither revive nor answer the owner's ask.

Two adjacent changes:

- **One identity per URL.** `capture` looks an item up by
  `reels.canonical_url` (the fetch cache's key): every YouTube shape is
  `youtube:<id>`, Instagram and TikTok drop the query string, the web drops
  only the fragment. Stored URLs are untouched; the first shape captured
  stays the item's URL. The ledger held no cross-shape duplicate when this
  shipped (`duplicate_identities_all_time: 0`), so nothing was migrated.
- **The intent window runs from presentation.** The sweep expires an
  intent ask 7 days after its first render in the hub digest
  (`outbox.presented_at`); an ask nobody has seen never expires.

### Owner decisions (2026-10-18)

- The YouTube playlist is not deliberate: it is a stepping stone. Owner's
  words.
- An interactive `ytk reels` pick is deliberate, an agent capture needs a
  note to skip the ask, and the brief is amended: recommended in the plan,
  built on the owner's "build step 3".

### Assumptions

- **A deliberate act is a judgment of worth.** The design rests on this:
  choosing a URL says "this belongs", and the question "why" adds little.
  Measured support is thin: of 21 owner captures, 15 already carried a
  reason, and the ask produced one owner sentence in 5 firings.
- **An empty reflex take does not make enrichment worse.** Not shown
  either way. The baseline below has 6 enriched items with an empty reflex
  take (all playlist videos answered "just want it"): 0 passed the grader,
  all 6 landed by owner override, against 6 of 17 grader passes for items
  with words. Fisher's exact p = 0.14, and source is confounded (every
  reflex item is a YouTube video). This is the number to watch.
- **Agent detection is an environment check.** Claude Code sets
  `CLAUDECODE=1` in every shell it starts; `AI_AGENT` is a cross-tool
  convention. Agents that set neither are treated as the owner. The
  owner's own `! ytk add` typed inside a Claude Code prompt runs in that
  shell and counts as an agent capture (the CLI says so in one line).
- **Dropped is terminal, so the CLI may write the revive.** The loop never
  picks a dropped item, so a surface writing the `captured` transition
  races nothing, exactly like a first capture. This bends P5 (surfaces
  insert events, the loop writes transitions) the same way `capture` always
  has.
- **The hub is opened.** Presentation-based expiry assumes the digest gets
  rendered. If it is not, passive items wait forever instead of dropping:
  the queue grows, nothing enters the corpus unasked.

### Limitations

- **Playlist items stay gated.** The playlist is a stepping stone, so sync
  stays passive; a playlist video enters without a sentence only when the
  owner later picks it in the hub or `ytk add`s it.
- **Takes stop being labels for silent deliberate captures.** The brief's
  "every owner sentence is a labeled example" loses the rows the ask used
  to collect on deliberate captures (one sentence per five asks). Empty
  reflex takes are rows, not sentences.
- **Identity covers YouTube ids and query strings only.** `http` vs
  `https`, `www.` vs bare host, trailing slashes on web pages, `m.youtube`
  shapes `youtube_id` does not parse, and the same content on two
  platforms are still distinct items.
- **A revived item re-runs the read.** A video whose captions or CDN links
  changed since the drop is read fresh; nothing from the dropped attempt is
  reused except the take.
- **The grader nag is untouched.** Step 3 unblocks none of the six owner
  items stuck today: all sit on "grader bounce, twice" or "transcript
  junk". Image carousels and silent reels still hit "transcript junk: no
  captions and no transcript", because the gate treats any post without
  speech that way; a gate change is a separate decision.

### The quality instrument

`scripts/ingest_quality.py` reads the ledger read-only and splits items by
their first take (words, reflex with no words, none). Baseline on a copy
of the ledger taken when step 3 shipped (all non-grandfathered items):

| cohort | items | enriched | first-round pass | enrich calls per item | bounce asks per item | landed by grader | landed by owner override |
|---|---|---|---|---|---|---|---|
| words | 24 | 23 | 0% | 3.8 | 1.61 | 6 | 11 |
| reflex, no words | 6 | 6 | 0% | 3.7 | 1.83 | 0 | 6 |
| no take | 29 | 0 | | | | | |

Top bounce checks: Grounding 51, concept grounding 25, Key moments 24,
What I do not want 21, Tags 12. Intent asks by surface: sync 38,
grandfathered 6, cli 4, hub 1. Expiries 25, never presented 12, stuck
parks 0, duplicate identities 0. Connections answers: approve 19, none 1,
strike some 1.

After about 15 deliberate silent captures have been enriched:

```
uv run python scripts/ingest_quality.py --since <ship date>
```

Regression means any of: the "reflex, no words" cohort's bounce asks per
item or override share rising above the words cohort's by more than the
baseline gap; a duplicate identity above 0; a stuck park; an expiry with
`presented_at` NULL; a revival by an actor other than owner. `ytk eval`
(retrieval) is untouched by step 3 and must stay green. With cohorts this
small the instrument catches large regressions only.

### Tests that pin it

`tests/test_capture_deliberate.py` (silent adds, per-source adds, hub
pick, quality gate first, passive surfaces, agent shell, answer, revive,
passive never revives, kept item untouched, identity across shapes,
expiry from presentation), `tests/test_reels_cli.py` (interactive pick
deliberate, `--all` not), `tests/test_loop_sweep.py` (expiry ages the
presentation). Mutation check: each of the ten behaviors above, removed
one at a time, fails at least one test.

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
- Measure a larger or MLX Whisper against base int8 on ten reels before
  changing the model.

## Order

1. Merge the fetch layer and step 3 (owner's go; same branch).
2. Run the quality instrument after about 15 deliberate silent captures.
3. Step 4 calibration, then the grader decision.
4. Step 5 as daily use asks for it.
