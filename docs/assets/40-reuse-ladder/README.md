# 40 — The reuse ladder

Rung 2 of #96: section 39 measured what goes in and what search brings back;
this section answers the acceptance question it deferred — **was anything
reused?** — by climbing the evidence ladder over claude-mem sessions and
session briefs. Still zero new instrumentation.

Two corrections drive every number:

- **Granularity.** Observation-level joins undercount: a session reads a note
  in one observation and edits code in another. At observation level the
  vault-read-and-modified count is 55, of which 49 modified only the vault
  itself (housekeeping). At session level the picture changes entirely.
- **Ritual vs elective.** ytk sessions are *instructed* to read `wiki/`,
  `inbox/memories/` and `projects/` at start — that is context loading. The
  elective signal, the one that means "captured knowledge was wanted", is a
  read under `sources/`.

## Figure 01 — the ladder and the calendar

Left, evidence per note, weakest claim to strongest: 671 embedded; 153 read
inside sessions (any folder, all time); **57 elective source-note reads**; 55
served to a genuine search (15-day window); **1 cited in a session brief** —
across all 56 briefs, which hold 2 genuine wikilinks total (both to one
LinkedIn draft) and 13 path references, mostly to wiki and project files. The
rung the issue named as the strongest available evidence ("a session brief,
commit, or generated note that links a retrieved source is a citation") is
the emptiest: **briefs describe work produced, not knowledge consumed** —
nothing in the brief ritual asks what was consulted.

Right, the same sessions on a continuous week axis: 45 elective source-read
sessions since May, 26 of which modified work outside the vault — and the
mass sits in the last five weeks. The loop closing is a *recent habit*,
coinciding with the study/library features and heavier agent use, not a
steady property of the system.

## What reuse actually looks like (paraphrased from session prompts)

- "read that note in the vault and tell me about his tooling" — a captured
  talk consulted mid-build
- "what did we take away from this video for our grove implementation" — a
  video's lessons pulled into a feature session
- a mechanistic-interpretability video ingested, then reviewed across two
  sessions that produced experiment-record sections
- an epicmap session reaching into ytk's vault for a remembered creator
- "distill one cool lesson from any N sources" — synthesis generated directly
  from the library

These are exactly the completed loops #96 exists to detect — and every one of
them is visible only through claude-mem's accidental `files_read` exhaust.

## Consequences for the event vocabulary

- `cite_or_copy` will stay empty unless the **brief ritual asks for sources
  consulted** — a one-line template change turns the emptiest rung into the
  strongest, at zero tax (the agent writes briefs anyway). Feature
  hypothesis, not implemented here.
- The elective/ritual distinction must be a first-class dimension of any
  `open`/`read` event — pooling them inflates reuse ~3x (125 vs 45 sessions).
- `create_from_sources` already happens (curricula, study decks, distills)
  and is currently indistinguishable from any other write.

## Limits

- `files_read` globs make 57 notes and 45 sessions floors, not measurements.
- "Produced work" counts any non-vault modification — scratchpads and skill
  files count; the one observation-level production-code edit is the floor
  on the strictest reading.
- Brief scan covers `projects/ytk` only; other projects' briefs (if any cite
  ytk notes) are unscanned.
- Windows differ by rung (search: 15 days; sessions: all time) and are
  labeled on the figure rather than normalized — the corpus was also growing
  the whole time.

Compute: `experiments/reuse_ladder.py` → `reuse_ladder_results.json`
(commit-stamped; no prompt or query text is persisted — dates, projects and
flags only). Figure: `scripts/plot_reuse_ladder.py`.
