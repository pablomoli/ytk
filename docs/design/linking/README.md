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

A neighbour table per note (doc-to-doc, top 5, cosine), refreshed on each
index, shown where the owner works: the hub's note and packet pages,
"nearby" with the cosine. One tap writes the link through the same apply
path, the argued clause generated at that moment. No daily ask stream: a
backfill that raised connections asks for 565 notes would bring back the
nag step 3 removed.

## Enrichment: in order of expected yield

1. **A deterministic anchor check before the grader.** Code checks each
   transcript citation against the cited span (token overlap within the
   ±90 s the adjacency check already uses) and moves it to the best span
   or flags it, before a model round is spent. First, replay it over the
   stored drafts against the anchors the owner corrected by hand: if it
   finds the owner's corrections, it earns its place. Frame citations
   cannot be checked from text.
2. **House rules from the owner's corrections in the field guide**: open
   on the claim, never the running order; label inference from frames as
   inference; label knowledge from outside the record as the owner's; say
   evidence gaps in the gaps field, not between the lines. Measured by the
   same bounce checks afterwards.
3. **Neighbours in the enricher prompt** (layer 2 above).
4. **The grader calibration** (ingestion step 4): first drafts never pass,
   and 18 of 30 landings were the owner overruling it.
5. **The storyboard sheet on the curator's YouTube path** (ingestion step
   5): "visual sources" bounces (8-11) on videos that had no sheet.

## Open

- Factual links: approved once as a list (decided, layer 1).
- Concept hub threshold: 2+ notes (decided, layer 1).
- Where the "nearby" panel goes first: the packet page or the note view.
