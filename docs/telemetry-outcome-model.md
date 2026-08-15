# Outcome model v0 — what a working second brain means here (#96)

Grounded in the measured baselines of sections 39 (trace inventory) and 40
(reuse ladder). Every claim below is anchored to a number that exists or a
patch that is named; nothing is aspirational vocabulary. This is v0: the
definitions are for the owner to correct, and the version bumps when they
change.

## Actors

Every event and every metric carries one of three actors. Pooling them is the
model's cardinal sin — the measured baselines differ by orders of magnitude.

| actor | definition | measured baseline |
|---|---|---|
| `user` | Pablo, through the hub | 2 typed searches ever; 554 hub captures in 16 days |
| `agent` | Claude working in a session (MCP `vault_search`/`vault_read`, CLI during sessions) | 33 genuine searches / 15 d; 45 elective source-read sessions; 153 notes read |
| `system` | pipelines acting on stored intent: eval gate, recall harnesses, profile/recs/study builds, nightly sync | 98.6% of the retrieval log |

The user's loop is **capture and curate**; the agent's loop is **retrieve and
apply**; the system's loop is **maintain and test**. The second brain "works"
when the user's captures flow through the agent's loop into work — the user
searching more is *not* a goal of this model.

## The evidence ladder

Ordered weakest to strongest. "Strong" means: hard to emit by accident,
interpretable without inference.

**Agent loop** (the loop that measurably exists):

1. served in search results — weakest; served is not used (33 events / 15 d)
2. note opened via `vault_read` — currently invisible to ytk; floor of 153
   notes known only through claude-mem's lossy `files_read`
3. **elective source-note read** inside a session — 57 notes, 45 sessions;
   the ritual/elective distinction is load-bearing (pooling inflates 3x)
4. source-read session modifies work outside the vault — 26 sessions
5. brief/commit/artifact names the source — 1 in 56 briefs today; becomes
   the top rung only if the brief ritual asks for sources consulted

**User loop** (mostly latent; evidence must be explicit to mean anything):

1. capture (554/16 d) — intent to save, nothing more
2. bucket/tag assignment at triage — deliberate sorting
3. authored thought (r >= 2) — 32 notes, 5% of corpus; the strongest
   existing user signal
4. explicit usefulness signal (keep/forget, "this answered it") — does not
   exist yet; the resurfacing design is its natural home

**System loop:** never counts as evidence of value. Its events are health
telemetry (freshness, failure rates) and must self-identify at write time.

## Outcomes by dimension

Each dimension: what "working" means, today's measurable proxy, and what
unlocks a real measure. Failure mode listed because activity is not value.

**Metabolism** — captures become owned knowledge. Proxy today: r >= 2 rate
(32/671), captures-with-thought at triage. Unlock: `annotate` +
`create_from_sources` events. Failure mode: counting captures (the 08-04
bulk drain is 344 "events" of zero metabolism).

**Recall** — the brain returns useful material when asked. Proxy today:
almost none — zero-result searches are unlogged, so misses are invisible;
3 reformulation chains are the only friction signal. Unlock: patch 2 below,
then miss-rate and reformulation become derivable. Failure mode: scoring
recall on eval replays (the gate measures ranking on known items, not
whether real questions get answered).

**Application** — knowledge feeds work. Proxy today: the ladder's rung 4
(26 sessions; recent and accelerating — the mass is in the last five weeks).
Unlock: sources-consulted line in briefs (rung 5 becomes real). Failure
mode: counting ritual reads as application.

**Generativity** — distant notes combine into new things. Proxy today:
qualitative only (curricula, distills, study decks observed in session
prompts). Unlock: `create_from_sources` carrying source ids. Failure mode:
counting links the enricher generates rather than links a person or agent
chose.

**Attention/identity** — interests tracked without equating capture volume
with attention. Proxy today: snapshot lifecycle events (stamped since #83:
47 birth, 36 merge, 18 split, 11 death, 9 restated), signal-level
distribution, fresh_note_count overlays. This dimension defines #83's
eventual price semantics; see below. Failure mode: the E24 lesson — r-level
weighting is partly medium weighting.

**Trust** — generated intelligence deserves confidence. Proxy today: the
profile eval score (BUMP) is the only calibration signal. Unlock:
`suggestion_accepted/rejected` + `profile_corrected` events at the surfaces
where suggestions render. Failure mode: silence read as acceptance.

**Health** — the substrate is trustworthy. Proxy today: capture error rate
6.3%, captured_at coverage 100%, fixture pollution in production logs.
System-actor telemetry; a prerequisite for believing any other number.

## The minimal event set (patches, not a platform)

The inventory's conclusion is that #96 needs five patches to existing
loggers before any new surface:

1. `actor` field (`user|agent|system`) on retrieval and capture events
2. log zero-result searches in `log_retrieval` (delete the early return)
3. `vault_read` event in the MCP server (path, actor, session id)
4. session id passed through to retrieval events
5. instrument traffic sets `YTK_RETRIEVAL_LOG=off` (eval gate, test suite)
   or a `source=instrument` tag — tagging at write time beats the forensic
   classifier section 39 had to build

Plus one ritual change, free of code: the session-brief template gains a
"sources consulted" line.

## What #83 may price, honestly

The attention model this issue owes #83, as constrained by the measurements:
capture volume alone cannot be price (bulk drains, medium bias). Candidate
components that are defensible today: decayed *elective-use* mass (reads,
serves, thought-authoring per theme) layered over decayed capture mass, with
lifecycle events as the chart's discrete annotations. Volume can stay
capture count — it is honest as *activity* so long as price is not derived
from it alone. To be settled after the patches produce a few weeks of
actor-labeled data.
