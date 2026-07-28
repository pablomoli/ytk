# /quiz — design

**Date:** 2026-07-27
**Status:** approved, ready for implementation plan

## Purpose

Close the retrieval gap in the second brain. ytk stores and searches well and never once asks a question — everything is pull, nothing is push. `/quiz` makes the vault ask.

Conceptual model: Khan Academy. Mastery per concept, hints before answers, retry as the place learning happens, and no penalty for absence.

## Relationship to `/study`

This is the **first buildable slice** of the `/study` system specified in `docs/study-manifesto.md` (branch `study-concept-deck`), not a parallel system. It implements the manifesto's practice loop and is shaped so it can become `/study`'s Practice surface without migration.

Manifesto constraints this design must honor:

- *"We attempt before reveal. We retrieve after time has passed."*
- *"Difficulty must have a purpose"* — effortful during practice, humane during acquisition.
- *"A return is an invitation, not a debt"* — no due queues, no streaks, no guilt.
- *"Sources remain inspectable"* — every correct answer traceable to source text.

## Scope

**In:** a markdown-only Claude Code skill that runs a ten-question session against one vault note, adapts to prior results, and persists per-concept mastery.

**Out:** ytk CLI changes, hub UI, scheduling daemons, the other three rooms. A `ytk study` command is the anticipated next step (approach B, deferred) — the state file is shaped for it, but no code lands now.

## Architecture

### Invocation

`/quiz <title-or-id>`

Resolution order:
1. Exact stem match against note filenames under `second-brain/sources/`.
2. `vault_search` on the argument.
3. If several plausible matches, list them and ask. **Never guess.**

If nothing resolves, say so. Do not generate questions from model memory about a paper that was not opened — that path teaches confident fabrications.

### Session flow

**1. Select.** Read the note's enrichment block (`## Thesis`, `## Key Concepts`, `## Insights`). Extract candidate concepts. Load `~/.ytk/study.json`:

- `fragile` concepts present in this note → highest priority
- `mastered` concepts → skipped unless `next_return` has passed
- `new` concepts → fill the remainder

Ten questions total.

**2. Ask.** Open response by default. The user may say "multiple choice" at any point; **that question only** is reoffered as multiple choice. The next question returns to open response. The setting never becomes sticky — asking for an easier format on one hard question should not quietly downgrade the whole session.

**3. Respond.**

- Correct → confirm, move on.
- Wrong or partial → **one hint** naming the gap without closing it → user retries → if still wrong, full explanation grounded in the source span.
- Enrichment selects *what* to ask; source text grounds *what is true*.

**Source text availability differs by note type** (verified 2026-07-27):

| Note type | Full text | Grounding route |
|---|---|---|
| `sources/youtube/` | `## Transcript` + `## Description` | search transcript for the concept |
| `sources/web/` | **none** — Thesis/Summary/Key Concepts/Insights only | WebFetch the `url:` in frontmatter |

If the fetch fails, ground in enrichment and **say so explicitly**. The user must know when they are being taught from a summary rather than a source.

**4. Record.** Update per-concept state. Show a short recap of what moved.

### Grading rule

Judge the **idea**, never the wording. "It packs several things into one neuron because there aren't enough" is fully correct for superposition. Vocabulary is not the skill under test. Partial credit is normal; a partial answer gets a hint aimed at the missing half, not a rejection.

## State

`~/.ytk/study.json` is the source of truth. Follows the existing `profile-rank.json` → `me/profile.md` pattern.

```json
{
  "version": 1,
  "concepts": {
    "superposition": {
      "state": "fragile",
      "attempts": 4,
      "correct": 2,
      "first_seen": "2026-07-27",
      "last_seen": "2026-08-02",
      "next_return": "2026-08-16",
      "sources": ["sholto-douglas-trenton-bricken-how-llms-actually-think"],
      "misconception": "reaches for 'one neuron = one concept' — the thing superposition denies",
      "reframe": "drawer holding socks, batteries, receipts. Landed immediately."
    }
  },
  "sessions": [
    {"date": "2026-08-02", "note": "towards-monosemanticity", "asked": 10, "correct": 7}
  ]
}
```

### State machine

| From | Event | To |
|---|---|---|
| `new` | correct first try | `mastered` |
| `new` | wrong | `fragile` |
| `fragile` | correct after hint | `recovering` |
| `fragile` | wrong again | `fragile` (misconception updated) |
| `recovering` | correct first try | `mastered` |
| `recovering` | wrong | `fragile` |
| `mastered` | `next_return` passes | eligible again |

### Adaptivity

`misconception` and `reframe` are what make adaptation real rather than decorative.

- `misconception` records *how* the user got it wrong, in their own phrasing — not a score.
- `reframe` records the framing that worked when they finally got it.

On a later session, a concept carrying a `reframe` is introduced **using that framing**. This is the difference between a quiz and a tutor.

### Returns are invitations

`next_return` is advisory. Skipping it accumulates nothing. Nothing is ever "overdue." The recap must never imply the user is behind. A stale concept simply reappears one day.

Spacing: roughly 2 days after reaching `recovering`, roughly 2 weeks after `mastered`. Approximate on purpose — this is not an SRS scheduler and should not become one.

### Vault mirror

`second-brain/study/mastery.md` renders the JSON for reading in Obsidian.

**Known limitation:** `study/` is not in `reindex_vault`'s `scan_dirs` (`ytk/vault.py:1203`), so this file is readable but not searchable until issue #147 lands. Documented rather than worked around.

## Failure modes

| Case | Behavior |
|---|---|
| Title doesn't resolve | Search, show candidates, ask. Never quiz from model memory. |
| Note lacks enrichment | Say so; offer raw text or bail. No silent degradation. |
| `study.json` missing | Create fresh. |
| `study.json` corrupt | Back up to `study.json.bak-<date>`, start fresh, report. Never a silent reset. |
| Session interrupted | Record what was asked. Partial sessions count fully; abandoning costs nothing. |
| Concept in several notes | One record; `sources` grows. Cross-source reinforcement is the point of concept-level tracking. |
| Fewer than 10 concepts available | Ask what exists; say so. Do not pad with trivia. |

## Verification

Real run against a known note:

```
/quiz attention approximates sparse distributed memory
```

Checks:
1. Resolves to `second-brain/sources/web/attention-approximates-sparse-distributed-memory.md`
2. Questions derive from the enrichment block's key concepts
3. At least one hint quotes or paraphrases actual source text, not the summary
4. `~/.ytk/study.json` is written and is valid JSON matching the schema above
5. A second run on the same note prioritizes anything marked `fragile` in run one

## Anti-goals

- **Not a streak tracker.** `habits.md` forbids new daily trackers; the manifesto forbids guilt mechanics. There is no streak field and there will not be one.
- **Not an SRS.** No due queue, no backlog, no accumulating debt.
- **Not a curriculum.** It quizzes what was actually read, in whatever order it was read.
- **Not a note generator.** It writes state, not knowledge notes. Concept notes remain hand-written.
