# The curator engine

Design for the redesign of passive ingestion, agreed 2026-08-29/30.
Status: DESIGN COMPLETE and locked 2026-08-30 (steps 0-5 all decided).
Implementation starts at plan P1 below; changes to this document after
the lock are amendments, stated as such. Research input:
`docs/research/2026-08-29-loop-shapes.md` (with the critic's verdict).
Diagram: `curator-engine.excalidraw`.

## Why

The corpus (746 source notes at the time of writing) carries a sentence
from its owner on 32 of them. Two writers put notes in the vault with no
human step at all: the playlist sync (`ytk/scheduler.py`) and profile-matched
auto-ingest (`ytk/autoingest.py`). The hub inbox has a thought box that does
steer enrichment, but the phone-side paths that dominate volume route around
it. Transcript quality is never gated: auto-caption garbage, wrong language
and failed frame extraction reach the prompt as a remark and never block.
No writer emits an argued link; `graph.py` computes similarity and never
writes it back. The daily digest is written every day and read by nobody.

The owner does not read the notes (80-90% never opened). The notes are what
the agent and search chew on. The product is the owner's standing knowledge
of what is in the corpus and how it connects, plus what is built on top of
it: the map, the galaxy, the experiments, the hub. Those lose their value
when the engine under them is flaky. Engine first, body later.

## The brief

- Nothing enters the corpus without passing the owner. When the agent is
  unsure it asks, and the item waits.
- Every item gets a sentence from the owner before enrichment: intent if
  unwatched, reaction if watched, a one-tap "just want it" for reflex saves.
  Enrichment is built on that sentence, not stamped with it afterward.
- The note argues its connections in a section tied to the thesis; links are
  proposed by the agent and approved by the owner, never written silently.
- The agent speaks on its own when it has something to say: relevance to
  what a session is doing, tension with a stance the owner holds, a theme
  being born, unfinished occasions, loved creators.
- ytk owns the loop. Claude is the engine inside it. Surfaces (hub, session
  hook, phone) render the agent's voice and post replies; none is required.
- Consolidate, do not add: fresh merges into the library, the digest goes,
  what's-new becomes the push channel.
- Every owner sentence is a labeled example for a future intent predictor;
  the design collects and does not model.

## Tiers

```
             owner (hub, session, phone)
                      |  answers, takes, dumps
                  +---+----+
  surfaces  <-->  |  voice |   outbox: asks + interjections, typed
                  +---+----+   inbox: replies; a reply is the resume event
                      |
                  +---+----+
                  |  loop  |   wakes on events, advances what it can,
                  +---+----+   asks when it cannot, stops on the breaker
                      |
     +---------+------+------+----------+
   capture  enricher   grader   connect      verbs: agents with contracts,
            (writes)  (judges) (proposes)    blame recorded per role
     +---------+------+------+----------+
                  +---+----+
                  | ledger |   SQLite WAL, append-only transitions,
                  +---+----+   activity log, takes, asks
                      |
                  +---+----+
                  | kernels|   native code, admitted only with a napkin:
                  +--------+   search sweep, density/ridges, embedding runtime
```

Each tier talks only to the one below it. The loop never opens a note; a
verb never talks to a surface; the ledger never calls a model. The tier
answers the performance question by position: the agent tier is I/O-bound
Python where correctness wins; the kernel tier is native and must carry a
theoretical-maximum figure beside its measured one before it is admitted.

## Rules that cut across tiers

**Separate state and blame.** Every transition records the actor (which
agent, in which role, or the owner), the reason, and what was looked at.
The enricher writes; the grader judges against a rubric file the owner
owns and the enricher never sees. They do not share a process's judgment.

**When unsure, ask, structurally.** `asking` is a state the machine cannot
leave without an `answered` row. An ask is a proposal (target state,
evidence, one line of why, accept / reject / edit), not an open question.
Asks accrue and are delivered as one digest per owner appearance. An
unanswered ask parks after a window sized from measured answer latency.

**Grader outside the worker; breaker outside the process.** The kill
switch is a separate launchd watchdog reading a kill file and rate-limit
counts, dropping the loop to an inert state. The loop cannot disable it.

## Verbs

| verb | input | output | corpus after |
|---|---|---|---|
| capture | URL, paste, memo, screenshot, DM item | a ledger row | nothing written |
| brain dump | free text from any surface | routed pieces (takes, journal lines, ideas, questions) | each piece where it belongs |
| annotate | item + owner sentence (intent, reaction, reflex) | a `take` row; enrichment input | note written on the sentence |
| read | item | evidence bundle: transcript with quality status, frames, description | nothing; gate may raise an ask |
| enrich | evidence + take | thesis, summary, concepts, insights, moments, tags | draft note |
| grade | draft note + rubric | pass, or bounce with reason | draft accepted or returned |
| connect | accepted note | proposed links with one-clause arguments | `Connections` section after approval |
| tell me about | item or topic | a read that argues and pushes back | nothing unless annotated |
| teach existing / new | concept | lesson from own sources; captures queued for gaps | concept note, mastery state |
| journal | a day | dated entry | `me/journal.md` |
| ask | (agent-initiated) | a typed proposal in the outbox | item waits |
| speak | (agent-initiated) | an interjection on one of the five triggers | nothing |

`journal`, `teach`, `quiz`, `distill`, `whats-new` exist today as Claude
Code skills under `~/.claude`. They become thin wrappers over ytk verbs so
any surface can call them.

## Item lifecycle

```
captured -> read -> asking -> answered -> enriched -> connected -> kept
                     ^  |                    |   ^
                     |  +-- timeout --> parked   |
                     |                           |
                     +---- grader bounce --------+
                                              \-> dropped (archived, down-ranked, never deleted)
```

`state` is never stored on the item; it is the last transition. `parked`
is distinct from `asking`. `dropped` archives and down-ranks; nothing is
deleted. Transitions to `connected` and `kept` require an owner answer until
the grader has caught real failures a dozen times without a miss; `enriched`
passes on the grader alone, which is why the grader's deterministic checks
come first.

## Asks (step 1, agreed 2026-08-29)

What "unsure" means, kind by kind. Triggers are deterministic wherever
possible so the grader tier can raise them without a model. One ask per
item at a time, ordered as listed: quality before intent before
connections. Every answer is a labeled row.

| kind | trigger | proposal | if parked |
|---|---|---|---|
| intent missing | item has no `take` | why this one? intent / reaction / just want it / drop | expires to `dropped` as reflex |
| transcript junk | no captions; auto-captions with a garble score; language not en; Whisper `no_speech` | retry with Whisper / keep with the warning / drop | waits; retry sweep may clear it |
| blind item | visual-heavy source with frames failed or no transcript | retry frames / proceed text-only / drop | waits; retry sweep may clear it |
| duplicate | same URL, or cosine above the measured near-dup baseline | merge into [[X]] / keep separate / drop | keep separate |
| grader bounce, twice | enricher failed the rubric two rounds | accept as is / say what is wrong (edit) / drop | waits |
| connections | connect has candidates with an argument each | approve these links / strike some / none | none written |
| stance tension | item contradicts a take, decision record or journal line | does this change your stance on X? yes (say how) / no / later | no |
| routing | a brain-dump piece fits two destinations | file under A / B | held in the dump |
| reflex sweep | 20+ items landed from one source with nothing from the owner | archive all / pick some / keep waiting | archive all |

Step 0 volumes (`docs/research/2026-08-29-step0-intake.md`): ~56 items a
week land, so "intent missing" alone is ~8 asks a day; the per-appearance
digest absorbs that, a per-item interrupt would not.

### Parked

An item that was asked and not answered within its window. It keeps its
ledger row and evidence bundle; nothing is redone. It is not in the vault:
no note, no embedding, no links. Every digest carries one line, "N parked,
oldest from <date>", so the pile cannot grow silently.

Unparked by any of four events, never by a plain timer:

1. The owner answers. An ask never expires; a late answer moves the item
   to `answered` and the loop advances it on that event.
2. A retry succeeds. The idle sweep re-runs the deterministic check that
   parked the item (auto-captions arrive days after upload; frame
   extraction recovers when the session is healthy). A pass returns the
   item to `read` with no ask.
3. Relevance. The `speak` triggers apply to parked items: a new capture
   lands near one, or a session works on what it is about. The agent
   re-raises it with that context.
4. The reflex sweep. Past a per-source threshold, one aggregate ask
   replaces N individual ones.

Only "intent missing" expires on its own, to `dropped` as a reflex:
archived with URL, title and the non-answer. Quality kinds never auto-drop.
`dropped` is not deletion; a re-capture of the same URL raises the
duplicate ask with "you dropped this on <date>, revive?".

The intent window starts at 7 days, stated as a guess: step 0 found no
instrument for answer latency. The `asks` table is that instrument; the
window is re-sized from four weeks of real answers.

## Contracts (step 2, agreed 2026-08-29)

**Enricher.** In: the evidence bundle from `read` (transcript with quality
status, sampled frames, description, caption), the owner's `take` (kind
and text), the tag vocabulary, the per-source bias. Never the rubric. Out:
the existing `Enrichment` model plus `evidence_gaps` (what could not be
seen, as a field) and `take_response` (one paragraph answering the take:
agree and add, push back, or name what the reason misses). Note spine:
`My take`, `Response`, `Thesis`, then the rest.

**Grader.** Two layers; never shares a prompt with the enricher.

- Deterministic, code only, every draft: schema valid; banned phrasing
  absent; every key-moment timestamp inside the duration and adjacent to
  matching transcript text; each key concept findable in transcript or
  description (fuzzy); concept count scaled to length; tags in vocabulary
  or new with a reason; near-duplicate cosine against the corpus below the
  measured baseline (kernel 1's first consumer); `take_response` present
  when a take exists. A failure bounces with the failing check named and
  spends no model call.
- Model, after the deterministic layer passes: reads the rubric, the draft
  and the evidence; returns pass, or bounce with a list of (rubric item,
  what fell short, where in the draft); spot-checks three summary claims
  against the transcript and bounces on an ungrounded one. Two bounces
  raise the "grader bounce, twice" ask.
- Model split, a measured starting point rather than a decision: enricher
  on Sonnet, grader on Opus, with the registered prediction that swapping
  them changes the bounce rate. Recorded as the least certain part of the
  design.

**Rubric.** `~/.ytk/rubric.md`, owner-written prose, versioned by hash so
every grade row names the version it was judged under. Sections: who the
note is for, what the owner enjoys reading, what is unwanted, thesis,
summary, response to the take, concepts, insights, moments, visual
sources, grounding, tags, exemplars. Every bounce quotes the rubric item;
a wrong bounce is fixed by editing the rubric, never a prompt in code.
Draft v1 was written by the assistant on 2026-08-29 and is corrected by
the owner over time.

**Activity row.** One table, every action by every actor: `item_id, at,
actor (enricher | grader | connect | loop | sweep | owner), action,
from_state, to_state, inputs (evidence hash, take id, rubric hash, prompt
version), output ref, model, tokens, duration_ms, reason (one line),
detail (json)`. Blame is a query.

**Kernel 1, scoped.** `ytk_kernel` (PyO3, maturin, built in
`hatch_build.py` beside the SPA) exposing `sweep(query, k)` over an int8
matrix exported from the store, promoted from `experiments/e41_kernel/`.
Consumers: the grader's duplicate check and `connect`'s candidate list.
Chroma stays until the kernel passes the #85 retrieval gate at parity. The
pre-registration (theoretical maximum at 19 MB, prediction, measurement)
is written before the crate is touched.

## The loop (step 3, agreed 2026-08-30)

**Host: the hub process, one instance.** The events already originate
there (ingest POST, memo POST, iMessage watcher, source pulls), it is
resident under launchd KeepAlive, and it is the surface the owner
watches. Hard prerequisite: #38 — an exclusive lock on `~/.ytk/hub.lock`
at startup; a second instance exits quietly. The loop is one worker
thread fed by the ledger.

**Wake: events, with a poll as the safety net.** In-process events set a
`threading.Event`. Out-of-process writers (CLI, MCP, the nightly capture
job) insert their row and nudge `POST /api/loop/wake`; a 60-second
`SELECT max(id)` poll catches a lost nudge. The idle sweep is "due if the
last sweep is older than N hours", checked on every wake and on start, so
laptop sleep coalesces missed runs instead of queuing them.

**Tick.** Next advanceable item — `captured`, `answered`, or `parked`
with a retry due; newest first for captures, answer order for answers.
One transition, one activity row, repeat until nothing is advanceable or
the tick budget (10 items or 10 minutes) is hit. The SDK's `max_turns`
bounds a single verb. Measured base rates: one enrichment p50 58 s
(YouTube p50 129 s, max 188 s over 63 timed captures); ~8 items/day is
~12 minutes of model wall-time.

**Single writer.** The loop thread is the only actor that writes
transitions. Every other process inserts into event tables only:
captures (unique on source+url), takes, answers (unique on ask id).
Double delivery is a no-op by constraint. Crash mid-transition: the loop
leases the item (`working_until`) before the side effect and writes the
transition after it; expired leases revert on restart and the verb
re-runs; verbs are idempotent (notes located by frontmatter url, drafts
keyed by item+attempt).

**Breaker, outside the process.** `com.ytk.watchdog` (launchd, every 5
minutes) reads `~/.ytk/loop-health.json` — written by the loop each
tick: last tick, items advanced, errors in window, rate-limit hits,
tokens today — and the kill file `~/.ytk/loop.kill`. Trips on 3+
rate-limit errors in an hour, error rate over threshold, the same item
advanced 3 times without a state change, or a daily token ceiling. A
trip writes `~/.ytk/loop.inert`; the loop checks the flag before every
transition and cannot clear it — only `ytk loop resume` can. Thresholds
start as stated guesses, re-sized from the activity table. Uncertainty
on record: whether `ResultMessage` carries `usage`/`duration_ms` under
subscription auth; if not, the token ceiling falls back to a call count.
`sdk.py` must stop discarding those fields either way.

**Stuck and drift.** Per-item `tick_count`; 3 without a state change
parks with reason "stuck". Drift (links per item, new tags per week,
bounces per rubric item) is a digest readout, not a trip.

**Watch.** No new surface: the activity table is the log, `ytk loop
status` prints health, the inbox page carries a one-line strip inside
the page, the voice digest carries the same line.

**Idle cost.** One thread blocked on an event, one SELECT a minute, no
model calls until an event.

**Registered predictions** (checked when it runs): P1 median
capture-to-ask under 3 minutes while the hub is up; P2 hub idle CPU
unchanged; P3 zero double-processed items across the first 100 captures
with #38 fixed and the process killed mid-tick twice on purpose.

## Voice and consolidation (step 4, agreed 2026-08-30)

**The outbox is a table, delivery is a view.** `outbox`: `id, kind (ask |
speak), subkind, item_id, created_at, payload (proposal: target state,
evidence summary, one line of why, options), presented_at, answered_at,
answer_ref`. A surface renders every open message whenever the owner
appears; that render is the digest, nothing is sent. `presented_at`
records seen-without-answering, which is the answer-latency instrument
step 0 found missing. Answers insert into the event tables; only the
loop transitions.

**Digest order, fixed:** asks by kind (quality first), speaks, one
parked line, one loop-health line.

**Renderers:**

1. Hub. `/` is the digest (decided: the front door shows what needs the
   owner). The digest page keeps the queue picker and gains ask cards
   (accept / reject / edit, controlled state) and the loop strip. Fresh
   merges into the library (`library.tsx` gains a recency-first section;
   the fresh route retires).
2. Session. The SessionStart hook adds a compact voice block: open-ask
   count, top three by age, speaks relevant to the session's project.
   MCP tools `voice_list` and `voice_answer` — inserts only.
3. Notification. One-line speaks ride the focus-aware notify that
   `ytk memo` already has.

**Skills: all new.** The voice verbs get new skills written for this
engine (digest/answer, annotate, tell-me-about, connect, teach,
journal-into-vault); existing `~/.claude` skills are not reused or
wrapped (decided 2026-08-30 — the owner keeps them separate). The new
skills are thin: each calls the ytk CLI/MCP verb and formats nothing the
verb does not return.

**Speak, computed where it is cheap.** Relevance-to-now at session
start; tension, accumulation, unfinished occasions and loved-creator
from the idle sweep. Every speak names its trigger.

**`$$`, resolved.** The marker becomes capture plus a take of kind
reflex (message text as the take when present): the intent ask never
fires, but the item still passes read, grade and connect. Speed kept,
bypass removed.

**Retired:** `append_daily_digest` and the `review-*.md` files; the
fresh route; the what's-new pull page behavior. The hub catch-up thread
and autoingest are already committed removals.

## Ledger and plans (step 5, locked 2026-08-30)

`~/.ytk/ledger.db`, SQLite WAL, migrations in the `ytk/db.py` style.

```
items      id, source, url, title, provenance, captured_at,
           payload_ref (evidence bundle), lease_until, tick_count
           UNIQUE(source, url)                  -- double capture is a no-op
activity   id, item_id, at, actor (enricher|grader|connect|loop|sweep|owner),
           action, from_state, to_state,
           inputs (json: evidence_hash, take_id, rubric_hash, prompt_version),
           output_ref, model, tokens, duration_ms, reason, detail (json)
           -- transitions ARE activity rows; state = the item's last row
           -- with a non-null to_state
takes      id, item_id, kind (intent|reaction|reflex), text, written_at, surface
asks       id, item_id, kind, proposal (json), created_at
answers    id, ask_id UNIQUE, choice, text, at, surface   -- insert-only
outbox     id, kind (ask|speak), subkind, item_id, ask_id, created_at,
           payload, presented_at, answered_at
snapshots  id, item_id, at, before_ref, after_ref
           -- any transition that rewrites a vault note; the vault is
           -- iCloud, not git, and this is the only undo
```

Transitions and the activity log are one table so state and history
cannot drift apart. Grandfathering: the 751 existing notes get `items`
rows with `provenance = grandfathered` and one activity row to
`kept-unlabeled`; no backfill asks — the unfinished-occasions speak
trigger surfaces the worth-revisiting ones at digest pace.

### Plans

Eight, each a `wt` worktree landing green on `just check`, in order:

| plan | delivers | unblocks |
|---|---|---|
| P1 | ledger + migrations + `hub.lock` (#38 fixed) + grandfather import | everything |
| P2 | capture unification: all six writers insert `items`, vault writes stop; `read` verb with the quality gate | P3 |
| P3 | asks + outbox + the hub digest (`/`), fresh into library | the first law live end to end |
| P4 | enricher/grader contracts, rubric wiring, `take_response`, activity rows with usage fields (`sdk.py` stops discarding them) | P5, P6 |
| P5 | loop thread + wake API + idle sweep + `com.ytk.watchdog` + `ytk loop status` | unattended operation |
| P6 | `connect` + the Connections section + snapshots | the argued links |
| P7 | kernel 1 (`ytk_kernel`, pre-registered) under the dup check and connect candidates | Chroma retirement path |
| P8 | new skills, session voice block, MCP voice_list/voice_answer, retirements | consolidation done |

After P3 the first law is enforced; everything later deepens quality.
The acceptance thread (cringelords end to end; the kill-it-mid-tick
test) runs after P5 and again after P8. Open issues absorbed by #197
are retargeted to their plan now that the spec is locked.

## One packet (step 6, shipped 2026-09-06, #212)

**The view.** The loop cuts one evidence view per bundle (`ytk/view.py`,
`evidence/views/<item>-<bundle_hash>.json`), immutable, hashed. `rendered`
is the one prompt block the enricher and the grader both receive; a test
pins that both prompts contain the identical bytes. `grounding_text` is the
one string the deterministic checks tokenize. `shown` and `openable` carry
the unit ids a claim may cite: `t:<seconds>` for a transcript line (the
second already printed on the line), `frame:NNN` across one numbering of
the sparse set and the dense tier, `sheet`. `not_shown` says in sentences
what the packet left out, and the same sentences ship inside `rendered`:
not shown is unverifiable, never ungrounded. The budget (frames shown,
evidence cap, sheet placement) is data on the view; the two caps that used
to live in the readers are gone. The sheet default is `none`, production's
behaviour before this step, until the sheet measurement moves it.

**The attempt.** `ytk/attempt.py`, `evidence/attempts/<item>-<n>.json`:
view hash, the take, the previous draft, the findings requested, the draft
out, the verdict out. `rendered()` is the header both roles receive after
the packet; it tells the teacher a change it asked for is not a new
objection.

**Invariants.** Student prompt = role text + `view.rendered` +
`attempt.rendered()` + vocabulary. Teacher prompt = role text + rubric +
`view.rendered` + `attempt.rendered()` + draft. `add_dirs` is `view.mounts`
in both calls. Enrich and grade rows carry `view_hash` and `attempt`; a
grade row whose view differs from its draft's is refused, not written. A
concept read off a frame ends with its unit (`[frame:002]`): a listed unit
skips transcript grounding and the teacher opens the frame; an unlisted one
bounces at zero cost. A key moment past the transcript cut bounces as
"cites outside the packet". The writer never sees the rubric: the one
asymmetry that stays.

**Headless surface** (P8 pulled forward): `ytk item`, `ytk ask list`,
`ytk ask answer`, `ytk view`, `ytk grade`; MCP `item_show`, `ask_list`,
`ask_answer`, `view_show`. One module (`ytk/headless.py`), wrappers with no
logic. Every "grader bounce, twice" and "budget spent" card carries
`view_hash` and `attempt`.

**Owed.** Sheet in `shown` or `openable`: count structured-output failures
against `none` on the bundles that carry a sheet (e501375 protocol). The
only number the model does not settle.

## Native kernels

Admission rule, from the Muratori note (`sources/youtube/why-performant-code-matters...`,
47:53): decide per part whether it can afford Python's ~100x amplification;
for the parts that cannot, structure around a C-backed library or compile
that part and call out to it. Every kernel ships with the E41 pre-registration
shape: theoretical maximum, prediction, measurement, disclosed approximations.

| kernel | replaces | why it is worth it | order |
|---|---|---|---|
| 1. search sweep (promote `experiments/e41_kernel/` to a PyO3 extension) | Chroma round-trip for the production store | removes a daemon under every search, grader check and connect candidate list; 19 MB int8 streams in ~1 ms | step 2 |
| 2. density and ridges (`ytk/ridges.py`) | chunked numpy KDE / SCMS / marching squares | turns the map from a batch picture into a live instrument (#107) | after step 5 |
| 3. embedding runtime (GGUF Qwen3-Embedding under llama.cpp or candle) | sentence-transformers on torch | measured first; only if >= 5x and it drops torch from the wheel | after step 5 |

Not native, on purpose: the loop, the ledger, the enricher and grader (they
wait on the model and the disk), parsing (I/O and embedding dominate),
`books_match.py` (a real 100x on an unwired feature).

## Road

| step | deliverable | decides |
|---|---|---|
| 0 | done: `docs/research/2026-08-29-step0-intake.md` | 56 items/wk, two daily bands, 6.7% Instagram pass-through; answer latency has no instrument |
| 1 | done: the Asks section below | nine kinds, ordered; parked semantics |
| 2 | designed: the Contracts section below; rubric v1 drafted at `~/.ytk/rubric.md`; kernel 1 scoped, not built | depth, taste, blame; first native consumer |
| 3 | done: The loop section below | hub hosts, single writer, event wake + poll net, watchdog breaker; #38 is a prerequisite |
| 4 | done: Voice and consolidation section below | outbox table + presented_at instrument; / is the digest; all-new skills; $$ keeps speed, loses bypass |
| 5 | locked: Ledger and plans section below | one activity table; grandfather without asks; eight worktree plans P1-P8 |

Acceptance thread, every tier once, unattended until it needs the owner:
"second brain cringelords" arrives, is read, the owner is asked why and
answers, the enricher writes on that sentence, the grader passes or bounces,
connect proposes and the owner approves, the note is written with a
`Connections` section, and the next session opens with something to say.

## Removals

`ytk autoingest` and `com.ytk.autoingest`; the vault-writing half of
`ytk sync` (it becomes a capture source); the hub catch-up thread that
re-runs sync; the daily digest writer; the fresh route; both JSON ledgers
(`~/.ytk/ingest-job.json`, `~/.ytk/batch_ledger.json`).

## Parked, with a slot

Intent prediction consumes the `takes` table. The visual sensor consumes
the `read` verb's evidence interface. Neither blocks the engine.

## What the research says works, and where each decision comes from

- Asks as structural gates, not model judgment; per-action approval decays
  (Anthropic, "How we contain Claude"). Batched digests per appearance
  (HumanLayer factor 6, Inngest suspend-with-timeout). Proposal shape
  (MindStudio, Thariq's report stage).
- Wake on checkpoints and blockers, not cadence (Anthropic, "Building
  Effective Agents"); event-advanced shape B over a heartbeat.
- Small distilled carry between ticks, not raw dumps (E6 measurement,
  Anthropic harness notes, 12-factor factor 5).
- Grader walled off from the worker (Karpathy three-file loop via the
  loop-engineering reel; Horthy; Armin and Ben). Deterministic checks first,
  LLM judge second, human calibration third (Arize). Remove the human only
  after a dozen catches without a miss (Karpathy slider).
- Breaker outside the process, failing inert; iteration caps default off
  in frameworks and runaway loops are the common failure (When Agents Do
  Not Stop; opsagent).
- Never delete; archive, invalidate, down-rank (Graphiti; issue #13).
- AI links are worthless unless the owner made them (ssp.sh); generated
  bulk degrades search, caught by the retrieval gate #85.
- Nobody surveyed combines a self-running loop over a corpus with a
  structural ask gate; the closest 2026 project files and links with no
  ask step.

## Open, carried into the steps

Event mechanism and host (step 3); ledger concurrency across parallel
sessions and iCloud (step 5); ask taxonomy (step 1); in-loop deterministic
grader for `enriched` (step 2); how owner answers become standing rules so
future asks shrink (step 2); the watch surface beyond logs (step 4).

## Appendix A: the cast, in plain words (added 2026-09-06, session 079)

Glossary by analogy, written after a night in which the enricher and the
grader were found reading different evidence three times over (accent
fold, evidence cap, frames mount; items 758, 215, 489, 534) and the grader
contradicted its own previous round (item 759). The contract amendment
that follows from it is gh #212; the progress view is #213.

**The runner, the read verb.** Goes out to the source and comes back with
a backpack. Never writes a word in the notebook. If the recording is blank
or garbled, the runner raises a hand before anyone starts working.

**The backpack, the bundle.** Everything the runner brought back: the
recording (transcript), the photos (frames, the whole roll, and the
contact sheet), the flyer (caption, description, chapters), and a receipt
listing what could not be fetched (gaps). Nobody works from the backpack
directly.

**The exam packet, the view.** The proctor takes things out of the
backpack and photocopies them, page numbered, one packet, two copies,
same bytes. The cover sheet says what was left in the backpack: "pages 41
to 80 not copied", "photos 3 to 41 in the box, ask to see them". Before
#212 there is no packet; each reader photocopies its own pages with its
own copier settings.

**The proctor, the curator and loop.** Runs one exam at a time. Hands out
the packet, collects the homework, gives it to the grader, records every
hand-off in the class register (the ledger). Decides how thick the packet
is (the budget). Never writes homework, never marks it. The only writer.

**The student, the enricher.** Writes the note from the packet and the
owner's sticky note. Never sees the answer key, on purpose. A new student
every round, with no memory: it is handed the previous homework and the
marks and changes only what was marked (b144705).

**The grader.** Two people. The spell-checker (deterministic layer):
mechanical, no judgment. The teacher (Opus): reads the answer key and
marks against it, every failing section in one pass (7805024). Under #212
the teacher also gets last round's own marks and reads the same packet as
the student.

**The answer key, the rubric.** The owner's handwriting, `~/.ytk/rubric.md`.
The teacher quotes it in every mark. The student never sees it. This is
the one asymmetry that stays.

**The sticky note, the take.** "Why I saved this." On the cover of the
packet. The homework has to answer it.

**The librarian, connect.** After the homework is filed, suggests which
shelves it belongs beside; the owner approves each cross-reference. Before
a page is written on, the librarian photocopies the old page (snapshot).

**The register, the ledger.** Every hand-off: who, when, how much ink,
what came back.

**Red marks, rounds, asks, ink.** A bounce is homework handed back with
marks. A round is one submission plus one marking. Two rounds, then the
proctor asks the owner. An ask is the proctor's raised hand, the only way
anything lands without passing: intent missing, transcript junk, blind
item, grader bounce twice, budget spent, connections. Tokens are two
things: the packet a reader can hold at once (context window; a two-hour
lecture fits) and ink (counted output; the per-item pad is eight calls,
`curator.ITEM_CALL_CAP`, and the daily school-wide ceiling is gone).

**What each one holds and lacks, before #212** (shipped the same night, see One packet above; the table stands as the record of why).

| who | holds | missing |
|---|---|---|
| runner | the source, the backpack | nothing else, by design |
| proctor | the register, the budget, the health line | the packet contents: never stored, so it cannot prove both copies matched |
| student | its own photocopy, the sticky note, the marks, the previous homework | the answer key (by design); the teacher's photocopy; photos beyond two |
| spell-checker | the homework, its own text extraction, its own dictionary | the photos entirely |
| teacher | the answer key, the homework, its own photocopy, two photos, the sticky note | the student's photocopy; last round's own marks; what the student read off the photos |
| librarian | the homework's thesis and summary | the sticky note (until #210) |
| owner | the ask card | what was shown, the trail, without SQL |

**Ownership.** State is owned by the proctor and lives on disk plus the
ledger. Nothing is passed between the student and the teacher: each is a
fresh process handed a read-only copy of the current attempt and view,
returns one result, exits. The proctor appends the result and, if there
is a next round, opens the next attempt from what is on disk. Views never
change for a bundle; attempts close when the verdict is written; history
is append-only. Every node (hub, CLI, MCP, a chat session) reads the same
files.
