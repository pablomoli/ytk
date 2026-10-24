# Linked notes and better enrichment: what the data says, what to build

Plan of record, 2026-10-18. Layer 1 is built on `feat/link-hubs`; the rest
is not. Measurements are
read-only over the vault, the ledger and the stored embeddings; no model
calls.

## The measured picture

**Links.** 796 source notes. 32 (4%) carry any wikilink in the body; the
median is 0. The 30 notes the curator landed are the exception: 19 of 30
link, median 1, 17 of them to other source notes. The other 766 notes can
never gain a link today: `connect` runs only on a fresh landing
(`curator.py:244`).

**The connect path** (`connect.py`): queries are the owner's take, the
thesis and one per key concept, through `store.search_all` (query path),
cut to cosine [0.50, 0.90), at most 5 candidates, one argued clause each,
then the connections ask. 29 runs, 8 found nothing in band (best
0.436-0.497). 21 asks: approve 19, none 1, strike some 1. Approved links
land in `## Connections` after the thesis. Known defects: "strike some"
in prose writes zero links (#215); the note is not re-indexed after links
are written.

**The writer never sees the vault.** The enricher's prompt is the packet,
the take and the previous round; no neighbour note. The rubric still asks
it for tension with what is saved and for connections, so a bounce for
"no links returned" (item 777, twice) is a bounce the writer cannot fix.

**Where linking signal already exists:**

| signal | reach | judgment needed |
|---|---|---|
| same creator (`uploader`/`channel` frontmatter) | 55 creators with 2+ notes, 181 notes | none |
| same named key concept, exact normalized name | 364 names in 2+ notes, 395 notes (50%) | which names are hubs (once) |
| doc-to-doc nearest neighbour (stored v2 vectors, mean per note) | 565 notes (71%) have one at cosine 0.50+, 292 at 0.60+, 95 at 0.70+; median nearest 0.564 | per pair |

Top shared concept names: manim 19, touchdesigner 11, fable 11, claude code
10, codex 9, blender 8, backpropagation 8, tmux 7, feature splitting 7,
cross entropy loss 7. 11,338 distinct names overall: most concepts are
specific to one note, as the field guide asks.

Doc-to-doc neighbours against the 26 approved links to source notes: 11
were the nearest neighbour, 19 in the top 5, 23 in the top 10. Circular:
those links were proposed by a similarity search in the first place, so
this is an upper bound on recall, not an estimate.

**Enrichment.** No first draft has passed the grader in any cohort (0 of
29 enriched items, `scripts/ingest_quality.py`). Of 253 bounce findings,
grounding (model and code layers together) is 98, about 39%; then key
moments 25, "what I do not want" 26 (bad opening 11, evidence gap hidden 9,
hedging 8, running order 5), tags 17, insights restating concepts 14. The
owner's own corrections in "say what is wrong" answers are mostly citation
anchors (a frame or timestamp pointing at the wrong place), then visual
description marked as inference, outside knowledge labelled as the
owner's, and opening on the claim instead of the running order.

## Linking: three layers by how much judgment each needs

### 1. Factual links (as built, 2026-10-18, branch `feat/link-hubs`)

Creator hubs and concept hubs, `ytk/hubs.py`. Deterministic, no model calls.

**Owner decisions.** Factual links are approved once as a list, not per
link: the owner reviews the candidate names, strikes the ambiguous ones,
and every approved name is written in one pass. Links are generated from
the list, so striking a name later removes all of its links. Nothing is
written for a name still pending. Threshold 2+ notes for both creators and
concepts; the list is sorted by note count, descending. The review lives in
the hub, on `/tags` under "Hub links".

**What counts as a name.**

- Creator: the first non-empty of `uploader`, `channel`, `author` in the
  frontmatter (web notes use `author`), compared case-insensitively.
- Concept: each `## Key Concepts` bullet, the text before the first `: `,
  bold markers stripped; normalized to lowercase ASCII letters and digits
  with everything else collapsed to one space. A name with no ASCII letter
  falls back to its Unicode word characters.
- The hub's display name is the most frequent surface form.

Re-derived with this code over the live vault (read-only): 796 source
notes; 55 creators over 181 notes; 364 concept names over 395 notes; top
manim 19, fable 11, touchdesigner 11, claude code 10, codex 9. Approving
everything would link 439 notes with 1,131 links and write 410 hub notes.

**Where links live.** Frontmatter properties appended after the existing
keys, never in the body:

```yaml
creator: "[[3Blue1Brown]]"
concepts:
  - "[[Manim]]"
  - "[[Ford circles]]"
```

Obsidian documents quoted wikilinks in text and list properties, and its
1.4 release notes say "Properties with links will now properly show in
backlink entries". The docs do not say whether the graph view or rename
updates follow property links; that part is unverified. The body, and
therefore every embedding, is unchanged: `strip_frontmatter` runs before
every `upsert_doc`, and YouTube vectors embed thesis and summary only, so
the retrieval gate is not touched.

**Hub notes.** `second-brain/links/creators/` and `links/concepts/`, one
per approved name, frontmatter `generated_by: ytk-hubs`, body a list of the
linked notes by vault path. Regeneration rewrites and deletes only files
carrying that marker. The folder is excluded from `ytk reindex`
(`scan_exclusion`, reason `generated`): an index of notes would answer
every query.

**Targets.** Basenames are resolved across the whole vault,
case-insensitively, because Obsidian resolves `[[name]]` by basename:

- A note of the same name under `second-brain/` outside `sources/` is
  treated as hand-made: links point at it and it is never written. Nine
  approved names would land on one today (Dwarkesh Patel, Welch Labs, Artem
  Kirsanov, Nelson Elhage, Scaling Laws, The Bitter Lesson, Attention Is All
  You Need, Towards Monosemanticity, Toy Models of Superposition). The
  Bitter Lesson also exists at the vault root, so Obsidian already has two
  candidates for that link; the review row names both.
- A clash with a source note, a note outside `second-brain/`, or another
  hub gets a kind suffix, as in `Manim (concept)`. Today one: the creator
  `marimo` becomes `marimo (creator)` because the concept claims the plain
  name first.
- The review row shows where each name will link, so a wrong target is
  struck before anything is written.

**Review state.** `hub_verdicts` in the ledger (migration 2): `kind`,
`key`, `verdict` (approve or strike), `at`, `judged_by`, `surface`.
Append-only; the latest row per name is the current verdict. Listed in
`docs/label-inventory.md`.

**Lifecycle.**

- `POST /api/hubs/apply` records the changed verdicts, then makes the vault
  match the list. Idempotent: a second run writes nothing.
- A note the curator lands runs the same apply (`curator._land`, after the
  note is indexed); a failure is an activity row `hubs-error` and never
  un-lands the note. Until a name is approved this is a single ledger query.
- A new name crossing the threshold appears in the list as pending.
- A rewrite keeps the note's mtime: the daily digest ranks notes by mtime,
  and a link is not new content.
- A frontmatter key `creator` or `concepts` holding anything other than
  quoted wikilinks belongs to a person and is never touched or overwritten
  (one note today has a hand-typed `creator:`).

**Limitations.**

- Aliases are out of scope: "sparse autoencoder sae" and "sparse
  autoencoders" are two names; so are a creator and the person behind it
  (`3Blue1Brown` gets a generated hub although `Grant Sanderson` exists).
- ASCII folding merges names that differ only in non-ASCII characters
  ("Measure μ" and "measure", "Diagonal matrix Λ" and "diagonal matrix"),
  and punctuation-only differences ("C++" and "C").
- Instagram notes name their creator in `username`, which is not read: 70
  creators over 237 notes if it were, instead of 55 over 181. Not built
  because the measured list and the decision were about
  `uploader`/`channel`/`author`.
- Only the curator's landing applies the list automatically. Notes written
  by other paths (`ytk add`, a reflect rewrite of Key Concepts, a note
  refresh that rewrites frontmatter) catch up at the next apply from the
  hub.
- Changed non-YouTube notes are re-embedded once by the next `ytk reindex`
  (its cache is a file hash); the vectors are identical because the body
  did not change.

### 2. Argued links on landing (the existing connect path, fixed)

As built, 2026-10-18, branch `feat/connect-fixes`. Four changes, one
commit each; the commit messages carry the measurements.

- **Strike some (#215).** Root cause: `apply_links` reads strike-some
  text as a JSON list of the targets to keep, the form the hub sends; the
  MCP answer to ask 87 was prose, parsed as zero survivors, and applied as
  none. Every surface now goes through one check in `asks.answer_ask`: a
  strike-some answer on a connections ask must be a JSON list of proposed
  targets, or it is refused with the targets named and nothing recorded
  (CLI and MCP reply with the guidance, the hub answers 422). Rows
  recorded before the check apply as none with a reason that says the
  answer was unreadable. Ask 87's surviving link was not re-applied.
- **Re-index after links land.** Body-embedded notes (everything outside
  `sources/youtube`) are re-embedded through reindex's own single-note
  path (`vault.index_vault_note`) right after `## Connections` is
  written; YouTube notes are not, because their vector is the draft's
  thesis and summary. Of 19 past applies, 12 were body-embedded. A failed
  re-index never fails the apply; the next reindex pass sees the hash.
- **Doc-to-doc candidates.** The landed note's unit-mean stored vector
  (`store.note_vector`) queries both collections (`store.search_vector`,
  raw cosine, no boost, no log) as one more source next to the take,
  thesis and concept queries; union by note, best cosine kept, same band
  [0.50, 0.90) and cap 5. Argue, ask and apply are unchanged. Measured on
  the 30 landed notes: 19 candidate lists change, 27 doc-to-doc
  candidates enter, the 4 empty runs stay empty, and 32 of 38 approved
  links survive the merged cap (37 on the query path alone, which
  proposed them).
- **Neighbours in the enricher prompt.** Up to 5 nearby notes (title,
  thesis, the owner's take on that note) after the attempt header, writer
  only, never in the view. Seeded by the take plus the source's title and
  caption/description/article on the first attempt and by the previous
  draft on a retry. `[[...]]` in a draft is unlinked in code. Item 777's
  real prompt (built, not sent): 4 neighbours, including the QR note the
  grader asked for, 2.2k characters, +31% on a reel's prompt.

Assumptions and limits:

- Raw cosine from the two sources is merged as one scale. Top-1 medians
  agree (doc-to-doc 0.608, query 0.598) but the two are different
  measurements: a document against documents, a query against documents.
- The approved-link comparison is circular in the query path's favour; the
  connect row now records each candidate's source (`via`, cosine), so
  approval rate per source is countable after a few weeks of answers.
- Neighbours come from search, so they inherit its blind spots: the 4
  notes with nothing in band get no neighbours either. Before the first
  draft there is no thesis; the seed is title and caption, weak for
  handle-titled reels with short captions.
- The grader cannot check a tension claim against a neighbour it never
  saw. Mentions are steered to `take_response` and insights, outside the
  grounding spot-checks.
- The rubric's Connections section still asks the draft for links the
  draft has no field for, so a "no links returned" bounce stays possible.
  The fix is a rubric edit (links come from the connect step), which is
  the owner's.
- Doc-to-doc surfaced listings and templates; `inbox/review.md`,
  `inbox/ideas.md` and any `_templates/` folder are now unlinkable.
  Session memories and project handoffs still qualify as targets; whether
  they should is open.

### 3. Argued links for the 766 older notes (exposure, not writing)

As built, 2026-10-18, branch `feat/nearby-notes` (on `feat/connect-fixes`).
Two commits; the messages carry the measurements.

- **Nearby, on demand.** `GET /api/nearby?note=` returns up to 5
  doc-to-doc neighbours: the note's stored vector (`store.note_vector`)
  through `store.search_vector` and connect's `find_candidates` with no
  text queries, so the band [0.50, 0.90), unlinkable paths, self
  exclusion and cap are connect's. Targets the note already links
  (`[[...]]` by basename, embeds excluded) drop before the cap. No
  neighbour table: on the live store, one request per source note, p50
  41 ms, p90 89 ms, p99 123 ms, max 655 ms. A table would save ~40 ms per
  open and go stale between a link and the next index.
- **Coverage.** 590 of 796 source notes (74%) get at least one nearby
  note, 350 the full five; 3 have no stored vector, 203 nothing in band.
  2,237 neighbours, cosine median 0.579.
- **Where.** The hub note viewer (`NoteViewer.tsx`, `/library` and the
  other routes that open it), as a "nearby" list above the "visually
  similar" strip: cosine, title, a "link" button. Not yet on the packet
  page.
- **The tap.** `POST /api/nearby/link` re-checks that the target is still
  nearby, runs connect's argue prompt once with that one candidate, and
  writes through `connect.write_links`, the same write the connections
  ask now uses: snapshot, merge into `## Connections`, re-index. The
  section merges instead of being replaced, so a tap and an ask answered
  later both survive. The viewer shows the clause; the neighbour leaves
  the list.
- **The record.** An activity row `actor owner, action nearby-link` at
  the click time, detail target, cosine, surface, clause, re-index
  outcome, error; the model's part is its own `connect` row (trigger
  nearby). No ask, no answer, no state transition. 778 of 796 source
  notes resolve to a ledger item (747 grandfathered, 30 curator landings,
  1 by url); the 18 that do not (journal, screenshots, 6 others) list
  their neighbours with no button. No item is minted at click time.
- **Concurrency.** The tap takes the loop's lease by compare-and-set
  (no tick counted) and refuses an item the loop holds.

Assumptions and limits:

- Doc-to-doc only. A note whose vector sits far from everything (203
  today) shows nothing, and the take, thesis and concept queries that
  connect runs on landing are not run here.
- YouTube vectors are thesis and summary; body-embedded notes move after
  a link lands (re-index) and their nearby list can shift with it.
- Titles come from frontmatter or the first heading; memory atoms and
  session records without either show their slug. Handoffs and session
  memories still qualify as targets (the open question from layer 2).
- The clause is argued from the note's thesis and its Commentary or
  Summary, and the model may decline; then nothing is written and the
  owner row says so. Whether a tap should be allowed to override a
  declined clause is open.
- The tap is a positive per-link judgment only. Rows not tapped are not
  negatives: the list does not record what was seen.
- The tap writes the vault from the hub process, outside the loop's
  single-writer path; the lease is the guard, and it only covers items.

## Enrichment: in order of expected yield

1. **A deterministic anchor check before the grader. Built, replayed, not
   wired.** `moments.check_anchors` reads every transcript citation (key
   moment stamps and `[t:N]` cites) against the span it cites, with the
   grader's tokenizer and its ±90 s window: *moved* when the cited span
   shares no content word with the claim and a span in the window shares
   two or more (IDF-weighted pick, landing on the strongest line);
   *unsupported* when no span in the window shares two; frame and sheet
   cites are counted and skipped. `scripts/replay_anchor_check.py` replays
   it read-only over the 137 stored drafts against 49 anchor errors read
   by hand from the ledger: the owner's own answers, grader findings the
   owner pasted into "say what is wrong", and grader-only findings.

   | labels | where the right anchor is | n | moved | to the right place (±5 s) | unsupported | left ok |
   |---|---|---|---|---|---|---|
   | owner's own | inside ±90 s | 3 | 1 | 0 | 0 | 2 |
   | owner's own | beyond ±90 s | 1 | 0 | 0 | 1 | 0 |
   | owner-endorsed | inside ±90 s | 5 | 3 | 2 | 0 | 2 |
   | owner-endorsed | not in the record | 2 | 0 | 0 | 2 | 0 |
   | grader only | inside ±90 s | 14 | 7 | 6 | 0 | 7 |
   | grader only | beyond ±90 s | 11 | 3 | 1 | 1 | 7 |
   | grader only | not in the record | 13 | 0 | 0 | 13 | 0 |

   False alarms: of 227 anchors on landed drafts that neither the owner
   nor the grader objected to, it moves 21 (9%) and calls 7 unsupported.
   Read by eye (not the owner's judgment), about 12 of the 21 moves look
   like real improvements and about 7 break an anchor that was right:
   claims whose key word is under four letters (`pwd`), misspelled
   transcript words (Pythogus, Dmenico), or a claim read off the screen.
   Against the grader: of 62 anchors it named across model-layer grades
   the check flags 29; of 121 the check flags the grader named 29.

   **Why it is not wired.** The owner's own anchor corrections are not
   what it finds. Nine of the owner's anchor answers (asks 70-86) are
   frame or on-screen re-anchors, which text cannot see; the three
   transcript ones inside the window (items 770, 774) are also on-screen
   claims, and it moved none to the right place. The one far one (34:53
   to 54:06) is the existing snap's case. Its hits are the grader's
   transcript findings on long videos (8 of 19 inside the window moved to
   the right place), at a cost of roughly one wrong silent move for every
   two right ones: too many to auto-move, and the unsupported verdicts
   mostly duplicate the grader's existing code checks (13 of 15 are past
   the packet's transcript, which "cites outside the packet" already
   bounces).

   **Assumptions and limits.** 49 labels and 227 negatives is a small
   sample; the 22 inside-window labels decide the verdict. "Let stand" is
   weak: the owner did not check every anchor. Labels were read by hand
   from prose, and targets are the grader's or owner's stated spans.
   Drafts graded before packets existed (#212) are replayed against an
   in-memory packet at the 80k cap they were read under, rebuilt from the
   bundle on disk today. What would move the needle for the owner's
   corrections is a frame check (the frame's time against the claim), not
   a better text match.
2. **House rules in the writer's instructions. Built; two mechanical rules
   wired before the grader.** `ytk/writer_rules.py` holds `HOUSE_RULES`,
   thirteen rules appended to the enricher's role text (never the
   grader's, which keeps judging against the rubric). Each pairs a
   sentence that was rejected on a real draft with what was asked for
   instead. `PROMPT_VERSION` hashes them, so every enrich row says which
   instructions it ran under.

   Mined read-only from a ledger copy: 18 bounce answers in the owner's own
   words, 6 that paste grader findings, and 253 bounce findings (59
   grounding and 38 concept-grounding among them). A count is the number
   of owner answers making that correction, then the grader findings.

   | rule | owner | grader | one example (owner's words unless marked) | field guide before |
   |---|---|---|---|---|
   | 1 open on the claim, not the medium | 4 | ~18 | "Open the summary on the claim, not 'The reel is a build log'" | "Never start with 'The video' or 'In this'", summary only |
   | 2 the argument, not the running order | 1 | ~12 | "Rewrite the summary as the argument, not the running order" | absent |
   | 3 cite the unit that shows it; key moments on the line, not the chapter marker | 10 | ~40 | "Content is right, pointers are wrong. Remap the citations exactly" | "cite only units the packet lists" |
   | 4 say only what the frame shows; mark the rest as inference | 7 | ~12 | "Cut every venue claim ...; the evidence shows a crowd, string lights and a lighting truss, nothing more" | reels only: "separate captured evidence from inference" |
   | 5 a visual piece gets its look described | 3 | 11 | "Add the visual layer the rubric asks for, marked as inference from frames" | absent |
   | 6 no outside knowledge; the owner's is labelled as the owner's | 2 | ~10 | "That identification is mine, from outside the record ... label them as owner-supplied" | "Nothing outside the packet can be cited" |
   | 7 who said it (host versus guest) | 0 | ~6 | grader: "The claim ... is Dwarkesh's, not Cotra's" | absent |
   | 8 name a gap exactly; no claims from an unseen stretch | 2 | ~12 | "there is no voiceover, the argument is in the caption, say so plainly" | "Never paper over a gap" |
   | 9 concepts in the packet's words | 1 | 38 code | "She never says 'binary encoding' ... Rename the concept" | absent |
   | 10 insights are what to do, not the concepts again | 0 | 14 | grader: "All three insights restate entries already in key_concepts" | stated, with the cover test |
   | 11 answer the whole take; correct a wrong premise plainly; no praise | 3 | 11 | "say plainly in take_response that my take guessed wrong" | "answer it directly", "if they asked a question, answer it" |
   | 12 tags: no near-synonyms, nothing unsupported | 2 | 17 + 4 code | "drop movie-rec and trim to the vocabulary" | "3-8 tags" |
   | 13 voice: no emojis, no programming analogies, no process talk, prose only | 0 | 4 | grader: the tag reason "which the grader flagged as needed for retrieval" | absent |

   Where the guide already stated a rule and drafts kept breaking it (1,
   8, 10, 11), the house rule sharpens the wording and carries a rejected
   sentence; nothing is restated twice.

   **The lint and its replay.** `writer_rules.lint` checks the mechanical
   subset with no model call. `scripts/replay_writer_lint.py` replays it
   over all 137 stored drafts against the first grade after each draft and
   any bounce answer on it. "Observed" means a model grade or an owner
   answer read the draft (96); a code-layer bounce alone stops before the
   prose is judged. Precision and recall are against what was said on
   observed drafts.

   | lint rule | flagged | on first drafts | observed | said | precision | recall |
   |---|---|---|---|---|---|---|
   | open on the claim | 44 | 18 of 29 | 25 | 12 | 10/25 | 10/12 |
   | the argument, not the running order | 16 | 5 | 9 | 10 | 3/9 | 3/10 |
   | banned words outside thesis and summary | 5 | 2 | 3 | 2 | 0/3 | 0/2 |
   | summary longer than five sentences | 6 | 0 | 2 | 4 | 1/2 | 1/4 |
   | frame-only claim past the visible, unmarked | 21 | 5 | 21 | 11 | 4/21 | 4/11 |
   | near-synonym tags | 25 | 8 | 17 | 10 | 9/17 | 9/10 |
   | process talk or markup in prose | 4 | 0 | 4 | 4 | 4/4 | 4/4 |

   Read by eye, all 15 opening "false alarms" are the construction the
   rubric bans ("The reel is", "The episode traces", "The creator
   explains", "The video visually distinguishes"): the grader named it on
   10 drafts and let it through on 15, sometimes on the next attempt of
   the same item, and the owner hand-fixed "The piece is" after accepting
   one of them. The label is what is imprecise there, not the check. The
   process check first matched the bare word "grader" and fired on a note
   about OpenAI's grader; it now matches only "grader flagged/asked",
   "rubric", "previous round/draft" and field markup.

   **Wired: open on the claim and process talk.** In `curator.advance_item`,
   after each draft, a hit on either is recorded as a `lint` row (actor
   grader, layer lint, shown as the spell-checker) and sent back as
   findings through the attempt header, the channel grader findings use,
   for one patch call; the grader then reads the patched draft. One fix
   per round, inside the item call cap, never an ask: a second miss goes
   to the grader as is. Historically this would have fired on 18 of 29
   first drafts, one Sonnet call each, before an Opus call that bounced
   them all.

   **Not wired, and why.** Running order (3/9: "walks through" and "closes
   with" are ordinary prose in a summary that does argue), frame inference
   (4/21: a word list cannot tell "technique" read off a title card from a
   technique guessed), summary length (n of 4) and banned words outside
   the two fields the grader's code checks (0/3) are too imprecise or too
   rare. Near-synonym tags (9/17, the rest by eye the same pairs the grader
   named elsewhere) is not wired because its general form, a bare tag
   beside a longer tag containing it, flags "ai" beside "ai-agents", and
   "ai" is one of the owner's own configured interest tags; the specific
   pair list is one pair, learned from the same sample it would be scored
   on. They stay in `lint` for the replay.

   **Assumptions and limits.** No model call was made: whether the house
   rules change drafts is a prediction until new drafts exist. Counts were
   read and clustered by hand from prose; "~" marks grader counts that
   depend on how a mixed finding is split. The lint's labels are
   keyword matches over findings and answers, hand-written from reading
   them, and the grader is an inconsistent labeller (above). The patch can
   fix an opening and regress nothing else only because a patch returns
   just the fields it changes. The rules carry real rejected sentences
   from this corpus; a rule worded around one item can over-steer the
   writer on unlike items, which only new drafts will show.

   **How to measure it.** Every enrich row records `prompt_version`
   (`b5f650421dfd` for first drafts, `2056c2a8a37a` for patches, at this
   commit). After twenty or so new items:

   ```bash
   sqlite3 ~/.ytk/ledger.db ".backup /tmp/ledger-copy.db"
   uv run python scripts/ingest_quality.py --db /tmp/ledger-copy.db --prompt-version b5f650421dfd
   uv run python scripts/replay_writer_lint.py --ledger /tmp/ledger-copy.db
   ```

   The first reads first-round pass rate and the bounce mix for items whose
   first draft ran the new instructions, against 0 of 29 before and a mix
   led by grounding (about 39%), "what I do not want" (26), key moments
   (25), tags (17) and insights (14). The second shows whether the
   wired lint still fires on new first drafts; if the rules work it
   should fire rarely, and its `lint` rows count the patch calls spent.
3. **Neighbours in the enricher prompt** (layer 2 above).
4. **The grader calibration** (ingestion step 4): first drafts never pass,
   and 18 of 30 landings were the owner overruling it.
5. **The storyboard sheet on the curator's YouTube path** (ingestion step
   5): "visual sources" bounces (8-11) on videos that had no sheet.

## Open

- Factual links: approved once as a list (decided, layer 1).
- Concept hub threshold: 2+ notes (decided, layer 1).
- Where the "nearby" panel goes first: the packet page or the note view.
