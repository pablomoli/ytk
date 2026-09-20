# Label inventory

Measured 2026-09-18, from the repo at `2538e18`, the live ledger and the live
Chroma store. Every number below was counted in that one pass; the snippets
that produced them are at the end.

## What this is

Every learned component in `ytk/` is a pretrained model used frozen:
Qwen3-Embedding-0.6B for search, Qwen3-Reranker-0.6B in `ytk/rerank.py`,
SigLIP-2 in `ytk/visual.py`, clustering plus one Claude call in
`ytk/synthesis.py`, and a prompted Claude curator. Nothing in the package
updates a weight. Several ideas on the table would change that: a taste model
moved by your behaviour, retrieval tuned to your sense of relevance, a learned
curator linker, opening the visual encoder's patch grid, time-aware video
embeddings. The first question for all of them is the same: how much labelled
signal exists.

A **label** here is a recorded human judgment that could one day teach a
model: you looked at something and said yes, no, this one, or wrote what was
wrong. Data that is only measured (an embedding, a hit rate, a grader verdict)
is not a label, however much of it there is. Two things in this inventory sit
on the border and are marked as such: the eval query set, whose answers are
known by construction rather than by your judgment, and the graded relevance
pairs, which were judged by a model.

This file holds counts, column names and category names only. The contents of
`answers.text`, `takes.text`, titles and URLs stay in the ledger.

## The inventory

| Signal | Count | Who judged |
|---|---|---|
| Ledger items | 790 (754 grandfathered, 36 captured since) | nobody; this is the denominator |
| Asks raised by the curator | 106 | the engine |
| Answers to asks | 92, of which 40 carry free text | you |
| Answers split | 33 say what is wrong, 19 approve, 18 accept as is, 9 intent, 8 just want it, 2 keep with the warning, 1 strike some, 1 reaction, 1 none | you |
| Answers of "drop" | 0 | you |
| Items dropped by an expired intent ask | 8 | nobody; a week of silence |
| Connection asks (the linker's decisions) | 21, proposing 42 links; 38 links approved, 4 not written | you |
| Takes | 31 (22 intent, 8 reflex, 1 reaction); 21 carry text | you |
| Distinct items with at least one answer | 31 | |
| Distinct items with a take | 31 (the same 31) | |
| Eval queries with a known answer | 156 (79 memories, 44 segments, 33 videos) | a model wrote the queries; the answer is known by construction |
| Graded query-document pairs (`qrels.json`) | 4,681 over the same 156 queries | `claude-haiku-4-5`; 20 pairs spot-checked |
| Current-state queries | 16 | derived from dated note pairs, no judgment |
| Map buckets (`grove_buckets.yaml`) | 10 buckets, 28 matchers (14 themes, 12 projects, 2 path prefixes) | you |

Asks by kind: 52 grader bounce twice, 30 intent missing, 21 connections,
2 transcript junk, 1 budget spent. Fourteen asks have no answer (12 intent
missing, 2 grader bounce). Eight of the intent asks ran out their seven-day
window: the sweep stamps the outbox row, writes no answers row, and moves the
item to `dropped` with an `expire` activity row marked `non_answer`
(`ytk/loop.py:568`). Silence is recorded, but as an event, not as a choice.

All 92 answers fall between 2026-08-31 and 2026-09-13, and 84 of them on two
days (46 on 09-06, 38 on 09-08). The takes cover the same span. The labels are
two sittings, not two weeks of steady behaviour; anything learned from them
would also learn the mood of those two sittings.

## Signal by signal

### Answers to curator asks

**What you did.** The curator holds an item and asks one question at a time.
You answer from the hub (`POST /api/outbox/answer`, `ytk/ui/server.py:398`),
the CLI (`ytk ask answer`, `ytk/cli.py:2922`), the MCP tool
(`ytk/mcp_server.py:312`) or chat. All four go through
`headless.ask_answer` (`ytk/headless.py:180`), which refuses a choice the ask
did not offer, then `asks.answer_ask` (`ytk/asks.py:117`). By surface: 26 mcp,
25 hub, 23 chat, 18 cli.

**Where it lives.** `answers` (`ytk/ledger.py:69`): `ask_id` (unique, so one
answer per ask, insert-only), `choice`, `text`, `at`, `surface`. The question
is in `asks` (`ytk/ledger.py:61`): `kind` and `proposal`, a JSON blob holding
`why`, `options` and the kind's payload. All 106 proposals parse as JSON.

**Shape.** A pick from a closed list of two to four options, plus optional
free text. The lists, from the code that raises each ask:

| kind | options | raised at |
|---|---|---|
| grader bounce, twice | accept as is, say what is wrong, drop | `ytk/curator.py:389` |
| budget spent | accept as is, drop | `ytk/curator.py:136` |
| intent missing | intent, reaction, just want it, drop | `ytk/asks.py:103` |
| connections | approve, strike some, none | `ytk/connect.py:486` |
| transcript junk | retry with Whisper, keep with the warning, drop | `ytk/evidence.py:142` |

Answers by ask kind: 50 grader bounce (33 say what is wrong, 17 accept as is),
21 connections, 18 intent missing, 2 transcript junk, 1 budget spent.

**What it could teach.** The 50 bounce answers are the closest thing here to
a preference signal on enrichment quality: a draft the grader rejected twice,
and your ruling on whether the grader was right. Read as a binary it is
17 accept against 33 reject, which is enough to estimate how often the grader
is stricter than you (about a third of the time, with a wide interval at
n=50) and not enough to train a grader. Two further limits:

- Only 24 of the 50 answered bounce asks carry the `attempt` and `view_hash`
  keys that tie the answer to the exact draft and packet it judged (the keys
  arrived with #212). For the other 26 the draft has to be inferred from
  activity order.
- The sample is censored. You only ever see drafts the grader bounced twice.
  Of 123 grade rows, 12 are passes, and no pass was ever shown to you for a
  ruling. There is no label for "the grader passed this and should not have".

"Drop" was offered on every one of the 106 asks and chosen zero times. The
only item-level negatives in the ledger are the 8 items dropped by an expired
intent window, and those say "did not answer in a week", which is a weaker
statement than "this does not belong in the library". Nothing here can teach
the second one.

### The free text: "say what is wrong"

40 answers carry text: 23 under say what is wrong, 8 intent, 6 accept as is,
and one each under strike some, none and keep with the warning. Length runs
from 24 to 3,000 characters, mean 490.

**What happens to it.** On a bounce ask the text becomes the first finding of
the next round, ahead of the grader's own list (`ytk/curator.py:291`), and
lands in the attempt file as `findings_in` (`ytk/attempt.py:32`). The next
attempt's `draft_out` and `verdict_out` sit in the same file. So each of the
23 is, in principle, a triple: the rejected draft, your correction in words,
the revised draft.

**What it could teach.** This is the richest signal in the system and the
hardest to use. A sentence of critique does not reduce to a target: it has to
be read by a model to mean anything, which is what the engine already does
with it, once, in the prompt. Twenty-three critiques is a fine few-shot set
for a grader prompt, or a test set for "does the revised draft address the
complaint". It is not a training set for anything.

### Connection asks

**What you did.** After an item lands, `connect` gathers candidate notes,
has a model argue each one, and asks you to rule on the survivors
(`ytk/connect.py:471`). The proposal's `links` list holds `target`,
`target_title` and `argument` per link. You approve the set, strike some, or
reject all; `apply_links` writes the survivors (`ytk/connect.py:499`).

**Counts.** 21 asks on 21 items, 42 links proposed (one to four per ask).
19 approve (38 links), 1 strike some (3 links), 1 none (1 link). The activity
log shows 19 `connect-apply` rows and 2 `connect-none` rows, so the strike
some answer wrote no links either. Upstream, the model argued 42 of 84
candidates; the 42 it declined are the model's call, not yours.

**What it could teach.** A linker needs to know what you reject. This holds
38 accepted links and 4 rejected, and the rejections came as two whole-set
decisions. 21 decisions is not a dataset, and a 90 percent approval rate
means a model that always says yes already scores 90. The strike some option
is where a per-link label would come from, and it has been used once.

### Takes

**What you did.** A take is your sentence about why an item is in the
library. It is written two ways. A thought typed into the hub's Add box rides
the capture (`ytk/ui/hub.py:935` to `ytk/capture.py:50`). Or you answer an
intent missing ask, and the answer is copied into `takes` with the kind mapped
from the choice: intent to intent, reaction to reaction, just want it to
reflex (`ytk/asks.py:41`, `ytk/asks.py:136`). 18 of the 31 takes share a
timestamp with an answer, so 18 came from asks and 13 from capture.

**Where it lives.** `takes` (`ytk/ledger.py:52`): `item_id`, `kind`, `text`,
`written_at`, `surface`. 25 hub, 4 chat, 1 cli, 1 mcp. 21 of the 22 intent
takes carry text (82 to 385 characters, mean 232); none of the reflex or
reaction takes do.

**Shape.** A three-way category plus a sentence. The category is the label
the engine doc has in mind when it says every owner sentence is a labelled
example for a future intent predictor (`docs/architecture/curator-engine.md:44`).
The take is also an input, not only a record: it heads every attempt
(`ytk/attempt.py:61`) and feeds the deterministic grader checks.

**What it could teach.** An intent-versus-reflex classifier over item
embeddings is the obvious reading, and 22 against 8 will not support it. The
class boundary is also soft. All 8 reflex takes came from answering "just
want it" to an ask, and another 8 items never got a take because the ask
expired. Those 16 are plausibly one population split by whether you happened
to click, which is a guess from the counts and not something measured.

### The eval query set

**What it is.** `eval/retrieval/queries.jsonl`, 156 lines, each
`{"query", "gold_id", "bucket"}` (`ytk/retrieval_gate.py:114`). The gold id
names one document in the namespace `vid::`, `mem::` or `seg::`
(`ytk/retrieval_gate.py:18`). `ytk eval` runs each query through the
production search path and reports hit@1, hit@5 and hit@10 against the gold.

**Who judged.** Nobody, in the sense this file cares about. The queries are
synthetic: a model wrote a half-remembered query for a note it was shown, so
the answer is known because the question was built from it
(`docs/research/encoder-audit/05-local-eval-results.md:23`). It measures
whether search can find a known item. It does not record what you consider
relevant.

**The files around it.**

- `baseline.json`: the stamped scores the gate compares against. Epoch v2,
  authored 2026-07-26, tolerance 0.02, overall hit@1 0.712, hit@5 0.904,
  hit@10 0.942, plus per-bucket scores and a provenance block (query file
  hash, corpus fingerprint, encoder revision, producing commit).
- `frozen_corpus.json`: the 11,005 document ids that existed when the
  baseline was stamped. Scoring is restricted to these so that vault growth
  cannot move the numbers (#111).
- `qrels.json`: 4,681 graded pairs over the same 156 queries, grades 0 to 3
  (1,856 / 1,421 / 638 / 766), each with a confidence (4,243 high, 414
  medium, 24 low). The judge is `claude-haiku-4-5-20251001` under prompt
  `qrels-v1` (`scripts/build_qrels.py`, loaded at `ytk/relevance.py:13`).
  Twenty pairs were spot-checked, 19 agreed. The file does not say who did
  the spot check.
- `candidate_pool.json`: the same 4,681 pairs as ids only, before judging.
- `current_state_queries.jsonl`: 16 rows (`query`, `gold`, `older`, `sim`)
  built from dated note pairs where the newest is gold
  (`scripts/r2_sweep.py`). The R2 sweep that used it was reported as
  under-powered at n=16.

**What it could teach.** The 4,681 graded pairs are large enough to fine-tune
a reranker or fit a fusion weight. They would teach the reranker to agree
with Haiku, not with you. As a measuring instrument the set is adequate: at
hit@5 near 0.90 and n=156 the standard error is about 2.4 points, so it sees
a five-point change and not a one-point change. As a training set for "your
sense of relevance" it holds, at most, the 20 spot-checked pairs.

### Map buckets

**What you did.** You wrote `~/.ytk/grove_buckets.yaml` by hand: ten named
buckets, each a list of matchers. A note belongs to a bucket if its project
slug, its interest-profile theme, or its path prefix is listed
(`ytk/mapdomains.py:168`). The file holds 12 project matchers, 14 theme
matchers and 2 path prefixes, none repeated across buckets, plus one global
`seed_floor` of 0.62. Both the map and the garden read it
(`ytk/mapdomains.py:46`, `scripts/build_map.py:45`).

**Shape.** A grouping, stated as rules rather than as examples. You did not
assign notes to buckets; you assigned projects and themes, and notes follow.

**What it could teach.** Expanded against the corpus it becomes a weak
ten-class label on every matched note, which could supervise a projection
that pulls your groupings together. The expansion was not run here, so the
number of notes each bucket reaches is not counted. The label is only as fine
as its matchers: a bucket with one theme says nothing about which notes
inside that theme are central.

## Pairs the corpus holds without anyone labelling them

These cost nothing to collect and are the realistic supply for anything
contrastive. Counts come from Chroma metadata on the current epoch (v2).

| Pair | Count | Source |
|---|---|---|
| Image with its title | 705 of 721 images carry a non-empty `title` | `ytk_visual`: 428 youtube, 265 instagram, 17 tiktok, 6 screenshot, 5 pinterest |
| Summary with transcript segment | 451 videos with a summary and at least one segment; 15,055 segments under them | `ytk_videos_v2` (453 docs, all with `summary` and `thesis`), `ytk_segments_v2` |
| Segment with its start time | 15,055 (`start` on every segment) | `ytk_segments_v2` |
| Thought with its note | 21 takes with text in the ledger; older `## My take` sections in vault notes not counted | `takes`; vault |
| Key moment with its timestamp | not counted | vault notes |
| Images waiting for an embedding | 1,719 | `ytk_visual_pending` |

Two cautions. By the pattern of `image_path`, 644 of the 721 images are
thumbnails (all 428 youtube, 199 instagram, 17 tiktok) and 71 are post
images; no extracted video frames are in the collection. A thumbnail is made
to sell its title, so the pairing is tighter than a frame-and-caption pair
would be and teaches a narrower thing. And the summary is itself model
output over the transcript, so a summary-segment pair is a model's reading of
the text paired with the text, not an independent description.

Other collection sizes, for reference: `ytk_memories_v2` 5,022. The v1
collections still exist (`ytk_videos` 316, `ytk_segments` 2,996,
`ytk_memories` 6,801) and are not the ones search reads.

## Candidate sources not yet counted

- **Claude Code session transcripts.** Sessions call `vault_search` through
  the ytk MCP server and then read some of the results with `vault_read` or
  `vault_fetch`. A query followed by which notes were opened is an implicit
  relevance signal, and the only one that comes from real use rather than
  from a synthetic query. Two caveats: the searcher is a model acting for
  you, not you, and an opened note is a click, not a verdict.

  > **Later (2026-09-20):** counted, with the owner's go, counts only.
  > 3,712 transcript files, 27 of them with a ytk vault call. 56
  > `vault_search` calls (48 distinct queries, median 8.5 words, median 6
  > results returned), 43 from a main session and 13 from a subagent, on 8
  > distinct days between 2026-08-23 and 2026-09-20. 13 of the 56 searches
  > (23 percent) were followed by a read of one of their own results; the
  > opened result sat at rank 1 ten times, rank 2 seven times, ranks 3 to 7
  > ten times. 73 of 308 returned sources are URLs, which a later
  > `vault_read` path cannot be matched against, so 23 percent is a floor.
  > The oldest transcript on disk is dated 2026-08-17: the transcripts are
  > pruned on a rolling window, so this source erodes and cannot be mined
  > later. The server logs `vault_read` (`ytk/mcp_server.py:31`, 204 rows
  > across 34 sessions since 2026-08-16, 85 of them `hot` or `index`
  > navigation) but does not log `vault_search`, so the durable copy holds
  > the click and not the shelf it was picked from.
- **Hub searches.** `log_search_query` (`ytk/ui/hub.py:434`) appends every
  query typed into `/api/search`. The log holds 2 rows, both from
  2026-07-17. Whether other hub search paths bypass the logger was not
  checked; on the evidence here, the owner's own typed searches are close to
  nonexistent and the agent is the vault's main searcher.
- **Brief citations.** 22 of 80 session briefs carry a Sources consulted
  section, with 77 wikilinks to 50 distinct notes. Of the 65 distinct notes
  the read log shows opened, 28 were later cited in some brief. Cited is a
  stronger statement than opened, and it is already being written down.
- **`## My take` sections and reflection answers in vault notes.** Thoughts
  written at ingest before the ledger existed, and the answers from the
  reflection loop (#98). `ytk/signals.py` already classifies notes by capture
  strength (passive, saved, plus thought, plus directive) from what is on
  disk. Not counted: the vault was out of bounds for this pass.
- **Capture itself.** Saving a reel, adding a video to the playlist, pasting
  a URL. It is the largest behavioural signal and it is positive-only: there
  is no record of what you saw and did not save. Not counted.
- **E7 readback responses.** The garden experiment logged forced-choice
  answers with a confidence to `e7-responses.jsonl` under the garden
  directory in `~/.ytk/` (`ytk/ui/server.py:1175`). These are your judgments
  about the map's legibility. Not counted: the file was outside this pass.
- **Attempt files.** `evidence/attempts/<item>-<n>.json` hold findings in,
  draft out and verdict out for every round (`ytk/attempt.py:25`). The
  activity log shows 127 enrich rows and 123 grade rows (87 model layer, 36
  deterministic; 111 bounces, 12 passes). The verdicts are a model's, so they
  are not labels, but they are what the 50 bounce answers would be joined to.
  The files themselves were not opened.
- **Hub usage.** Which search results were opened, which feed cards were
  dismissed. Whether the hub logs any of this was not checked.

## How to refresh these numbers

All read-only. The ledger is opened with `mode=ro` because the hub's loop
holds it live.

Ledger:

```python
# python3
import sqlite3, json, collections, os
c = sqlite3.connect(f"file:{os.path.expanduser('~/.ytk/ledger.db')}?mode=ro", uri=True)
q = lambda s: c.execute(s).fetchall()
for t in ("items", "asks", "answers", "takes"):
    print(t, q(f"select count(*) from {t}"))
print(q("select provenance, count(*) from items group by 1"))
print(q("select kind, count(*) from asks group by 1 order by 2 desc"))
print(q("select choice, count(*) from answers group by 1 order by 2 desc"))
print(q("select count(*) from answers where text is not null and trim(text) <> ''"))
print(q("select choice, count(*) from answers where text is not null and trim(text) <> '' group by 1"))
print(q("select a.kind, n.choice, count(*) from answers n join asks a on a.id = n.ask_id group by 1, 2"))
print(q("select surface, count(*) from answers group by 1"))
print(q("select min(at), max(at) from answers"))
print(q("select substr(at, 1, 10), count(*) from answers group by 1"))
print(q("select count(distinct a.item_id) from answers n join asks a on a.id = n.ask_id"))
print(q("select a.kind, count(*) from asks a left join answers n on n.ask_id = a.id where n.id is null group by 1"))
print(q("select kind, count(*) from takes group by 1"))
print(q("select kind, count(*) from takes where text is not null and trim(text) <> '' group by 1"))
print(q("select min(written_at), max(written_at) from takes"))
print(q("select count(*) from takes t where exists (select 1 from answers n where n.at = t.written_at)"))
print(q("select action, count(*) from activity where action in ('enrich', 'grade', 'expire', 'connect-apply', 'connect-none') group by 1"))
links = collections.Counter()
for p, ch in q("select a.proposal, n.choice from asks a join answers n on n.ask_id = a.id where a.kind = 'connections'"):
    links[ch] += len(json.loads(p)["links"])
print(dict(links))
```

Eval set:

```python
# python3, from the repo root
import json, collections
rows = [json.loads(l) for l in open("eval/retrieval/queries.jsonl") if l.strip()]
print(len(rows), collections.Counter(r["bucket"] for r in rows))
qrels = json.load(open("eval/retrieval/qrels.json"))
print(len(qrels["labels"]), collections.Counter(x["grade"] for x in qrels["labels"]), qrels["judge"])
print(json.load(open("eval/retrieval/frozen_corpus.json"))["count"])
```

Buckets:

```python
# uv run python, from the repo root (the system python3 has no yaml)
import yaml, os, collections
d = yaml.safe_load(open(os.path.expanduser("~/.ytk/grove_buckets.yaml")))
print(len(d["buckets"]), collections.Counter(k for b in d["buckets"] for k, v in b.items() if isinstance(v, list) for _ in v))
```

Chroma, only after `just chroma-status` reports healthy. This lists and
counts; it does not go through the `_*_collection()` helpers, which create a
collection when one is missing:

```python
# uv run python, from the repo root
from ytk import store
c = store._get_client()
for col in sorted(c.list_collections(), key=lambda x: x.name):
    print(col.name, col.count())
vis = c.get_collection("ytk_visual").get(include=["metadatas"])
print(sum(1 for m in vis["metadatas"] if (m or {}).get("title")))
print(sum(1 for m in vis["metadatas"] if "thumb" in ((m or {}).get("image_path") or "").lower()))
```

The full pass, including paging 15,055 segment metadata rows, took about one
second against the local server. No model was loaded.

## What the numbers mean

There is enough here to measure with and not enough to train on. 156 queries
with 4,681 graded pairs is a working yardstick for retrieval. 92 answers is a
working yardstick for the curator: it can say how often you overrule the
grader and how often you approve the linker. None of it, at this size, moves
a weight in a direction that can be trusted. The largest class of answers in
the whole system is 33 rows.

The richest labels are the hardest to learn from. The 23 written critiques
say exactly what was wrong with a draft, and a sentence is the form a model
can least easily be trained against. The easiest labels to learn from, a
binary pick, carry the least: approve came back 19 times of 21, and drop came
back never. A signal that is nearly always yes tells a model almost nothing,
however many times it is collected.

So the shape in which a decision is captured matters more than collecting
more of them in the current shape. Three things the present shapes leave out,
each visible in the counts above:

- **No negatives.** Zero drops, eight expiries, four rejected links, no record
  of things seen and not saved. Every idea that ranks or filters needs
  something to push away from.
- **No per-element judgment.** Approve and none rule on a set of links;
  accept as is rules on a whole draft. Strike some, the one per-link option,
  was used once. A label on the set cannot be divided among its members
  afterwards.
- **No judgment on what passed.** You only rule on drafts the grader bounced
  twice and links the model chose to argue. What the models let through
  without asking is unlabelled, and that is where a model's blind spots live.

The unlabelled pairs are a different matter: 705 image-title pairs and 15,055
segments under 451 summaries exist today at no cost to you. An idea that can
be fed by those (the visual encoder, time-aware video embeddings) is not
waiting on labels. An idea that needs your judgment (taste, relevance, the
linker) is waiting on a capture shape that records it, and the two sittings
in the ledger are the evidence for what that shape should fix.
