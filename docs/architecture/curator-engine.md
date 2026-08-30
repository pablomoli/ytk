# The curator engine

Design overview for the redesign of passive ingestion, agreed 2026-08-29.
Status: design approved at the tier level; steps 0-5 below each produce
their own decision before code. Research input:
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
| 3 | loop shape, host, event mechanism, breaker | shape B tested against 0-2 |
| 4 | voice and surface consolidation | outbox, hub renderer, hook renderer, retirements |
| 5 | ledger schema, written spec, worktree-sized plans | locked last |

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
