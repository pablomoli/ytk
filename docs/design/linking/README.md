# Linked notes and better enrichment: what the data says, what to build

Plan of record, 2026-10-18. Nothing here is built. Measurements are
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

### 1. Factual links (no judgment per link)

Creator hubs and concept hubs. A hub note per creator with 2+ notes and per
concept name in 2+ notes; each source note's frontmatter creator and its
Key Concept names become wikilinks to the hub. Deterministic, no model
calls, and it backfills every note at once: from 4% of notes linked to
about half.

- The concept list needs one review: exact matching keeps genuine hubs
  (manim, tmux) and also ambiguous ones (fable, claude). The review is a
  one-time list of 364 names, or fewer at a 3+ threshold.
- Aliases are unmeasured: "sparse autoencoder sae" and "sparse
  autoencoders" are two names today.
- Linking in the body changes the indexed text of non-YouTube notes
  (memories embed the body); YouTube vectors embed thesis and summary only.
  The retrieval gate runs either way.
- **Owner decision:** the brief says links are "never written silently".
  Whether a factual link (same creator, same named tool) counts is the
  owner's call. If it does, layer 1 becomes one batch approval of the hub
  list, not a per-link ask.

### 2. Argued links on landing (the existing connect path, fixed)

- Fix strike some (#215) and re-index after links are written.
- Doc-to-doc neighbours next to the query path as a candidate source.
- Give the enricher the top 5 neighbours (title, thesis, owner take) so
  the draft can argue tension and connections from the whole draft, not
  only the thesis. Links still go through the connections ask; the
  rubric's demand becomes meetable.

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

- Factual links: silent or approved once as a list?
- Concept hub threshold: 2+ notes (364 names) or 3+?
- Where the "nearby" panel goes first: the packet page or the note view.
