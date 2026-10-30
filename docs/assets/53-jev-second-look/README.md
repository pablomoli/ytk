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

## Reading

**The Noul panel is wet, the Choice panel is dry.** A Noul is answered alone
and returns P(yes) on its own scale, so twenty of them can all be bright; a
Choice's probabilities sum to one. Full text made the Nouls wetter, not sharper
(more topical overlap, more yes), which is the "large state full of irrelevant
detail" edge TypeSafe's own jaggedness page describes.

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
- The serif face has no glyph for →, − or ×; figure text uses ASCII.

## Next

The 16 disagreements are the finding. The next rung is not more Jev calls; it
is the owner ruling on the 22 rows blind (`owner-labels.md`, candidates listed
without marks), which turns click labels into judged relevance and lets the
same two sidecars be re-read without a single new request.

## Reproduce

```bash
uv run python scripts/jev_rung0.py collect            # 84 calls, needs TYPESAFE_JEV_KEY
uv run python scripts/jev_rung0.py collect2           # 56 calls
uv run --with matplotlib python scripts/jev_rung0.py draw
uv run --with matplotlib python scripts/jev_rung0.py draw2
```
