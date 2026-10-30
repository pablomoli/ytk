# 53 — Jev, second look: does a decision model's brightness land where the agent clicked?

Rung 0 of the Jev program. One picture before any null or bar, on the owner's
rule that an experiment earns its gate only after a legible picture exists.

## The question

ytk's searcher is the agent, not the owner: 106 `vault_search` calls across 40
sessions since 2026-08-16, all tagged `actor=agent` in the retrieval log. In 22
of them the agent then opened one of the served hits within 15 minutes (the
`vault_read` log carries the same session id). Those 22 clicks, plus 6 bare-id
lookups the agent ran before ingesting a video, are the only retrieval labels
the system holds that nobody had to write. Rung 0 asks: when Jev (TypeSafe's
System One model, `jev-1.14.0`) scores today's top-20 for each of those
searches, does its brightness land on the note the agent opened more often
than the served rank already does?

## Method

`scripts/jev_rung0.py`; the API client is `scripts/jev_client.py` (stdlib
`urllib`, every call appended to `~/.ytk/logs/jev_calls.jsonl` with latency and
token usage). `cases.json` freezes the 28 inputs. Searches run through
`store.search_all(n=20, rerank=False, actor="probe")`, so the retrieval log
marks them as instrument traffic (section 39).

Two rounds over the same served candidates:

- **Round one** (`rung0.json`, figure 01): Jev sees exactly what the MCP tool
  shows the agent — title plus the 200-character excerpt. Three requests per
  case: 20 Nouls plus an "any?" Noul; one Choice over the 20 plus `none` in
  served order; the same Choice with the options reversed (TypeSafe documents a
  first-option lean). 84 requests, 291,823 input tokens, $0.012, median 151 ms.
- **Round two** (`rung0b.json`, figure 02): Jev reads the full document Chroma
  embedded — the text the ranking actually saw (median 1,638 chars, max 8,000;
  the heaviest case is ~23k tokens, inside the 64k per-request limit). Every
  question type in one request, plus the reversed Choice. 56 requests, 823,158
  input tokens, $0.035, median 249 ms for a 10–26k-token request.

Vault files were not sent: a YouTube note with its transcript is median 32 KB
(p90 94 KB, max 257 KB), twenty of which exceed the per-request limit and would
need the long-context header the docs call slower and less accurate.

Questions, verbatim in the sidecars. Noul: "Is `candidates.cNN` the note
someone who searched for `query` would open?" with true/false criteria.
Choice: "Which candidate holds what `query` asks for?", options described by
title, plus "No candidate holds it." The `gated` panel is Noul × (1 − P(none)):
the Choice's abstention as a row-wide gate on the Noul's per-candidate scale.

## Figures

- `01-second-look.png` — snippet context. One row per search sorted by where
  the opened note sits today (the cyan outlines form a staircase), columns are
  served rank, cell is P(yes). Panels: Noul per candidate; Choice plus none;
  strip of any / none / none reversed / same winner.
- `02-stored-text.png` — stored-text context. Panels: round one's Noul for
  reference; Noul on stored text; Choice on stored text; gated.
- `03-stability.png` — the same 84 requests run twice (|ΔP| histogram), and
  every Choice option's probability in served order against reversed order.
- `04-wetness.png` — per search, how many candidates the Noul admits at 0.5,
  snippet against stored text; and the opened note's own P(yes) against the
  median of its 19 neighbours, with its rank inside the row.
- `05-latency.png` — every call in the ledger, latency against input tokens,
  with the #86 budget and the local reranker's measured medians.

- `06-graded.png` — against graded relevance. Left: the grade of the note each
  arm ranks first, one row per search, with the clicked note's grade as an
  arrow. Right: mean nDCG@20 per arm over the shuffle null.

Figures 03–05 are drawn by `scripts/plot_jev_second_look.py` from the
sidecars and `~/.ytk/logs/jev_calls.jsonl`; figure 06 by
`scripts/jev_judge_score.py` from `judged-relevance.json`; no requests.

## The graded ruler

The click label was the open question, so the 22 searches were graded blind.
Three fresh Claude readers (the session model) each took 7–8 searches, saw the
query, the request the agent was working on where a transcript held it, and
the full stored text of all 20 candidates in served order with nothing marked,
and graded every candidate 0–3 (holds it / part of it or buried / adjacent
topic / unrelated), naming the best. 440 graded pairs, `judged-relevance.json`,
`judged_by` recorded. These are model judgments of real agent queries over full
text; they are not the owner's, and the inventory lists them as such.

Each arm is an ordering of the same 20 candidates: served (cosine), Jev Noul
and Jev Choice on snippets, both on stored text. Null: 1,000 random orderings
per search, scored the same way.

| arm | mean nDCG@20 | first note holds it (3) | first note ≥ 2 | vs served, wins/ties/losses | mean gain, bootstrap 95% |
|---|---|---|---|---|---|
| shuffle null | 0.604 ± 0.023 | | | | |
| served (cosine) | 0.816 | 10/22 | 13/22 | | |
| Noul, snippet | 0.835 | 8/22 | 13/22 | 14/0/8 | +0.019 [−0.057, +0.094] |
| Choice, snippet | 0.834 | 8/22 | 14/22 | 10/2/10 | +0.018 [−0.039, +0.083] |
| Noul, stored text | 0.958 | 12/22 | 19/22 | 19/0/3 | +0.142 [+0.067, +0.224] |
| Choice, stored text | 0.939 | 12/22 | 19/22 | 18/2/2 | +0.123 [+0.051, +0.208] |
| the agent's click | | 7/22 | 11/22 | | |

Reading. Served order already sits nine null standard deviations above
shuffle, so the baseline is real. On snippets Jev adds nothing the interval can
see. On the text the embedder ranked, Jev's Noul lifts the mean from 0.816 to
0.958, wins 19 of 22 searches, and puts a note graded 2 or better first in 19
of 22 against served order's 13. The click, the label everything before this
was scored against, was the worst ranker in the table: it reached a grade-3
note 7 times in 22. That is the measurement behind the earlier guess that the
clicks were browse labels.

Caveats, in order of weight. n = 22, and the interval is wide. Three readers
means three sets of habits; grades are comparable within a reader's searches,
and two readers flagged the same two kinds of difficulty (bag-of-terms
queries where no note holds everything; a query where "none" was defensible).
The readers and the two stored-text arms read the same bytes, so a reader's
notion of relevance and Jev's could share blind spots that the snippet arms
and served order do not. And the cost of this arm is the cost of sending the
full stored text: 10–26k tokens and about 250 ms per search.

## What was measured

| | snippet (fig 01) | stored text (fig 02) |
|---|---|---|
| brightest Noul is the opened note | 9/22 | 8/22 |
| brightest Choice candidate is the opened note | 8/22 | 6/22 |
| declared Choice winner is the opened note | 6/22 | 6/22 |
| served rank 1 is the opened note | 6/22 | 6/22 |
| Choice says `none` on ids absent from the store | 5/5 | 4/5 |
| Choice says `none` on the id in the store but never served | 1/1 | 1/1 |
| served and reversed Choice agree on the winner | 25/28 | 24/28 |

Repeatability (round one run twice, `rung0-run1.json` vs `rung0.json`): median
|ΔP| 0.000, p90 0.020, max 0.09 over 560 Nouls; identical Choice winner 28/28.

Ranks were stable: 20 of the 22 opened notes sit at the same served rank today
as on the day of the search; two moved from 1 to 2.

Context effect, measured (figure 04): candidates with P(yes) ≥ 0.5 per search,
median 0 → 1. The opened note's own P(yes), median 0.24 → 0.39; the median of
its 19 neighbours, 0.07 → 0.08. The opened note's Noul rank inside its row,
median 2 → 3, first in 9 → 8 rows.

Latency (figure 05): 168 round-one calls median 151 ms, 56 round-two calls
median 241 ms, slowest call 396 ms, at 2–5k and 8–26k input tokens. The local
Qwen3 reranker measured in #86 sits at 7.7 s (depth 10, 512 tokens) and 18.6 s
(depth 30) against a budget of +1 s per search.

## Reading

**The Noul panel is wet, the Choice panel is dry.** A Noul is answered alone
and returns P(yes) on its own scale, so twenty of them can all be bright; a
Choice's probabilities sum to one. Full text made the Nouls wetter, not sharper
(more topical overlap, more yes), which is the "large state full of irrelevant
detail" edge TypeSafe's own jaggedness page describes.

> **Later (same day, figure 04):** the sentence above was an eyeball reading
> of figure 02 and the measurement contradicts it. At a 0.5 threshold the
> median search admits 0 candidates with snippets and 1 with full text; the
> opened note gained +0.15 while its neighbours gained +0.01. Full text lifted
> the right note more than the crowd. What read as "wetter" was the `punch()`
> gamma lift brightening the 0.2–0.4 band, which the colour bar discloses.
> What full text did not do is change the opened note's rank among its
> neighbours (median 2 → 3, first in 9 → 8 rows). The sentence stands as
> written; the number is the finding.

**Full text changed what Choice believes is there.** With snippets, Choice
said `none` on about ten of the 22 opened rows and `any` sat at 0.1–0.85. With
stored text, `any` rose to 0.7–0.93 on almost every opened row, `none` went
dark, and Choice committed to a specific candidate — in 16 of 22 rows not the
one the agent opened, several at 0.8–0.96. Some of those picks read as better
than the click (the memory recording the filing of issue #150 over a session
brief that mentioned it); some as worse (a shadowbox memory over the reel that
literally shows tapping a table to control a Mac). The picture cannot
adjudicate, because the label is a click, not a judgment: several opened notes
are briefs and claude-mem summaries the agent opened to browse.

**The one clean result is abstention.** On ids never in the store Jev said
`none` 5/5 with snippets and 4/5 with text; the miss is the row whose query
carried a topic the vault does hold ("LG TV webOS debloat"), where Jev picked
an LG debloat note — a literal reading of a query that mixed an id with a
description, and arguably correct. On the id that is in the store but never
surfaces when searched by id string, Jev correctly said none of the served
twenty is it.

**Edge against position: none yet.** 9/22 and 8/22 against rank-1's 6/22 is a
difference of two or three rows at n=22. No bar was set and none is claimed.

## Corrections made during the section

- The first render counted `QGWKCaglSBI` as absent because the check looked at
  the served list; it is in the videos collection and does not surface for its
  own id. `in_store` now queries the collection; `served_today` is separate.
- "Choice picked it" in the first verdict meant the declared winner; the shared
  counter now reports the brightest candidate cell per arm, and the verdict
  says "Choice top candidate". Both numbers are in the table above.
- The serif face has no glyph for →, − or ×; figure text uses ASCII, and the
  log axis in figure 05 carries plain tick text for the same reason.
- Figure 04 was first titled "Full text lifts the crowd, not the note the
  agent opened", written from the figure 02 impression before the panel was
  drawn. Its own data said the opposite; the title now follows the data, and
  the reading above carries the annotation.

## Next

The 16 disagreements were the finding of rounds one and two; the graded ruler
resolved most of them in Jev's favour on full text. `owner-labels.md` stays as
the blind sheet should the owner want to overrule the readers on any row.

Rung 1 now has a measured shape to register against: on the 156 frozen gate
queries and the 4,681 graded pairs, served order against Jev Noul on stored
text, the bar set from this section's gain and #86's latency budget before the
first request. Rung 2's stability bar tightens to what figure 03 showed.

## Reproduce

```bash
uv run python scripts/jev_rung0.py collect            # 84 calls, needs TYPESAFE_JEV_KEY
uv run python scripts/jev_rung0.py collect2           # 56 calls
uv run --with matplotlib python scripts/jev_rung0.py draw
uv run --with matplotlib python scripts/jev_rung0.py draw2
```
