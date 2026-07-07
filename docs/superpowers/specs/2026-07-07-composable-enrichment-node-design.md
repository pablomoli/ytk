# Composable Enrichment Node + Eval Harness

Date: 2026-07-07
Status: design, approved for planning
Scope: "B" (node + Tier-1 eval harness). Out-of-scope items tracked in ytk issues #46-49.

## Context

The 2026-07 enrichment audit found ytk's enrichment prompt is honest and dense
(97.7% claim faithfulness, ~11 named specifics per 100 words, negligible hedge
language). The real defects were mechanical: a 512-token embedding cliff (fixed
in 9aec222 via per-section part vectors, which is Anthropic's published
Contextual Retrieval technique) and a flat cap of 8 key_concepts that saturated
42 of 60 sampled notes, dropping named tools the user would later search for.

Enrichment logic is currently spread across five near-identical functions:
`enrich`, `enrich_tiktok`, `enrich_instagram` (ytk/enrich.py), `enrich_web`
(ytk/ingest.py), and `enrich_journal` (ytk/imessage.py). They already share the
`Enrichment` pydantic schema and two always-on composable fragments,
`_note_block()` and `_vocab_block()`. This design generalizes that existing
concatenation into one node, removes the concept cap via Chain-of-Density, and
pairs the node with an evaluation harness so prompt changes are measured, not
guessed. The audit's core lesson is that prompt quality degrades silently; the
harness is the instrument that makes it visible.

## Goals

1. One enrichment node, invoked per source, replacing the five `enrich_*` bodies.
2. A user-editable tone preamble as the only user-facing steering surface.
3. Chain-of-Density replacing the flat cap of 8, scaling coverage to content.
4. A Tier-1 eval harness ("preview on 5 notes") that gates prompt changes with a
   pairwise judge, reference-free faithfulness, and a bootstrapped win-rate.

## Non-goals (tracked separately)

- open_questions -> inbox deferral loop (#46)
- opt-in Chain-of-Verification mode (#47)
- Tier-2 corpus-scale eval + adversarial query set; larger embedding model (#48)
- memories-collection 512-cliff fix (#49)
- Merging memo routing into enrichment (rejected by recon; routing stays a
  separate cheap step producing MemoResult).

## Component 1: the enrichment node

`enrich(content: str, source: str, user_note: str = "", config: EnrichConfig | None = None) -> Enrichment`

- `source` is one of a fixed set: `youtube | tiktok | instagram | web | journal`.
  Every ingest path already knows its source unambiguously, so dispatch is
  deterministic (no LLM router). The five existing `enrich_*` functions become
  thin wrappers that call `enrich(..., source=X)` and are retained as the public
  API so call sites (cli.py, scheduler.py, ingest.py, imessage.py) are untouched.
- The `Enrichment` schema is unchanged.
- `EnrichConfig` carries the user's tone preamble (loaded from settings) and is
  optional so tests and callers can omit it (defaults to no tone).

### Prompt composition (fixed assembly order)

```
[TONE PREAMBLE]   from config; user-editable in settings; empty if unset
[BASE SKELETON]   fixed: task framing + Enrichment schema contract
                  + anti-fluff rules + Chain-of-Density instruction
[SOURCE BIAS]     selected by `source`: built-in per-source handling
[USER NOTE]       existing _note_block(user_note)
[VOCAB]           existing _vocab_block()
[CONTENT]         the transcript / caption / article / thread
```

- **Tone preamble** is the sole user-editable layer. It shapes voice only
  ("write terse and technical, like notes to my future self"). It is placed
  ABOVE the base skeleton so the anti-fluff and faithfulness rules always follow
  it and cannot be edited away. Presence-only for v1 (set or unset); a numeric
  strength dial is a possible later refinement.
- **Source-bias fragments** are built-in constants, one per source, encoding
  content quirks (e.g. TikTok: "audio may be mostly music, lean on visible
  text/actions"; instagram: "slides are visual, name the aesthetic/technique";
  journal: the self-chat framing). Not user-editable.
- The existing `_note_block` / `_vocab_block` behavior is preserved verbatim.

### Guardrail against tone fighting anti-fluff

A tone like "be enthusiastic and punchy" could reintroduce the praise language
the audit confirmed is absent. Two defenses: (1) anti-fluff rules live in the
fixed base skeleton below the tone and are never editable; (2) the eval harness
scores specificity and faithfulness, so a tone edit that degrades density is
caught in the preview before it is saved.

## Component 2: Chain-of-Density

Replace the "max 8 key_concepts / key_moments" instruction with a CoD-style
directive in the base skeleton: produce increasingly dense passes, each listing
named entities the previous pass missed, then merge into a final list whose
length scales to the content (a 60-minute talk yields 15+, a short reel 3).
Single call, no latency multiplier. Applies to both key_concepts and
key_moments. This is also the harness's first test case (does CoD beat cap-of-8
on the 5-note preview?), which calibrates the harness before it is trusted on
subtler changes.

## Component 3: the eval harness (Tier-1 "lab")

New module `ytk/enrich_eval.py`. Compares two candidates on a frozen fixture set:
CHAMPION (current prompt/config) vs CHALLENGER (an edit). Challenger enrichments
are generated into a scratch space and never written to the vault or chroma.

### Units (each independently testable)

- `load_fixtures() -> list[Fixture]`: a versioned set of ~5 notes for Tier-1,
  stratified by source (at least one long talk, one short reel, one IG carousel)
  so CoD and source-bias fragments are both exercised. Each fixture carries the
  note's stored raw transcript (ground truth) and its current enrichment.
- `generate(fixture, config) -> Enrichment`: runs the node with a given config.
- `judge(a, b, transcript) -> Verdict`: a stronger model (Sonnet by default)
  scores two enrichments against the fixed rubric (below), order-swapped;
  a win counts only if consistent across both orderings (removes position bias).
- `faithfulness(enrichment, transcript) -> FaithScore`: hand-rolled FActScore.
  One Claude call decomposes key_concepts + insights into atomic claims and
  labels each SUPPORTED / INFLATED / UNSUPPORTED against the transcript.
  Anthropic-only, no new dependency. Works at n=1.
- `bootstrap_winrate(verdicts) -> (rate, lo, hi)`: bootstrap CI over the
  per-note wins. At n=5 the interval is intentionally wide, signaling "smoke
  gate, not ship decision".
- `ledger_append(entry)`: appends each challenger's scores vs champion to a JSON
  leaderboard (ytk lightweight-state convention), turning noisy small samples
  into a longitudinal signal.

### The judge rubric (drafted here; blocking prerequisite)

Fixed, version-controlled judge prompt. It asks the judge to prefer the
enrichment that better satisfies, in priority order:

1. **Named specificity** - more concrete tools, commands, APIs, papers, numbers,
   proper nouns; fewer abstract topic-words. (The audit's primary quality axis.)
2. **Faithfulness feel** - no claims that read as beyond what the source states;
   ties broken toward the more conservative enrichment. (FActScore is the
   quantitative backstop; this is the judge's qualitative read.)
3. **Non-redundancy** - concepts/insights that add information vs restating the
   summary or each other.
4. **Retrievability** - would this let a future reader who half-remembers the
   content find it (episodic-recall framing)?

The judge returns a winner (A / B / tie) plus a one-line reason per dimension.
Verbosity is explicitly NOT a merit; longer is not better.

### Surfaces

- CLI: `ytk enrich-eval [--source S] [--note PATH ...]` runs a champion-vs-
  challenger comparison and prints win-rate + CI + faithfulness delta, appending
  to the ledger.
- Settings preview: editing the tone preamble (or a fragment) triggers the
  5-note comparison in-app and shows win-rate + CI + faithfulness delta BEFORE
  the edit is saved. This is the "preview on 5 notes in settings" surface.

### Explicit exclusions

- recall@k / MRR is NOT a Tier-1 metric (ceilinged at 1.0 at this corpus size).
  Retrieval claims require the hardened adversarial query set in #48.
- No n=5 preview is a ship decision; it is a regression/obvious-win smoke gate.

## Testing

- Node: unit tests that each `enrich_*` wrapper composes the expected prompt
  order and passes the right source-bias fragment; tone preamble appears above
  the skeleton; schema output validates. Existing enrichment tests must pass
  unchanged (the wrappers preserve behavior).
- CoD: a fixture with many entities yields more than 8 concepts; a sparse one
  yields few.
- Harness units: `judge` order-swap consistency, `faithfulness` labels a known
  inflated claim, `bootstrap_winrate` returns a wider interval at smaller n,
  `ledger_append` round-trips. Judge/faithfulness LLM calls are stubbed in unit
  tests; a single opt-in integration test exercises the real path.

## Sequencing

Node + CoD first (the wrappers keep call sites stable), then the harness, with
CoD as the harness's first real evaluation. open_questions (#46), CoVe (#47),
Tier-2 (#48), and the memories cliff (#49) follow as separate specs.
