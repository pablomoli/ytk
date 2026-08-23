# ytk settings — what does what

Companion to the hub's `/settings` page. Everything here persists to
`~/.ytk/config.yaml`; the page is a validated editor over that file.

## The tags, untangled

There is **one tag namespace**: the `tags:` frontmatter list on every note in
the vault. What looks like "three kinds of tags" is one destination with two
producers, one gate, and one cleanup layer:

```
                       PRODUCERS
  Haiku enrichment ────────────────┐          (coins open vocabulary,
                                   ▼           ~400 tags and counting)
  /inbox annotation chips ────► note frontmatter tags:
  (hub.tags — your curated         ▲
   shortlist, one tap at queue     │
   time)                           │
                                   │
  GATE: filters.interest_tags — if non-empty, a video is only ingested
  when enrichment produces at least one matching tag. Empty = allow all.
                                   │
  CLEANUP: /tags merge decisions land in ~/.ytk/tag-aliases.yaml and are
  applied everywhere tags are written, forever — if enrichment re-coins a
  retired variant, it lands as the canonical tag.
```

So:

- **hub.tags** (Hub section) — the shortlist of chips shown in /inbox. Purely
  an input convenience: whatever you tap gets written into the note's
  frontmatter tags, same field enrichment writes to. Keep it small; it is the
  vocabulary of *your intent at capture time* (`build-idea`, `reference`),
  not topics — enrichment already covers topics.
- **the ~400 enrichment tags** — not configured anywhere. Haiku coins them
  per note. You garden them after the fact with [Tag cleanup](/tags) (merge variants) —
  accepted merges hold forever via the alias map.
- **filters.interest_tags** (Ingest filters) — a pre-write gate on `ytk add`.
  Non-empty means "refuse videos unless enrichment tagged one of these".
  This is the only tags field that can *reject content*. Most setups leave
  it empty and curate at the queue instead.

## Section by section

### Hub
- **host / port** — where the daemon binds. Changing either needs
  `ytk ui restart` (the page tells you).
- **tab icon** — the character served at /favicon.svg for every hub page.
- **tags** — see above: /inbox annotation chips.
- **pinterest feeds** — board RSS URLs pulled into the queue on refresh.

### Fetch cadence
Per-source auto-pull throttle in minutes. The hub pulls sources when you
load a page, but never more often than this (bot-shaped traffic gets
accounts flagged). "Pull all sources now" bypasses every window once.
Per-source last-pull times are shown live.

### Interest model
Parameters for `ytk profile` synthesis (second-brain/me/profile.md):
- **alpha** — how much your own signal (thoughts, saves) outweighs passive
  consumption. Fitted empirically 2026-07-05: 7 is the plateau start; 0
  disables weighting.
- **explicit_min** — minimum thought-carrying items (r >= 2) before the
  explicit interest channel activates. Below it, profile is implicit-only.
- **cluster range** — min/max theme clusters the synthesis may produce.
- **content sources** — which non-YouTube source folders feed the profile.

### Map color rules
Ordered query -> color rules for /map, first match wins (Obsidian Groups
model). A rule paints every note whose path, title, or tags contain the
query. Presets save/load whole rule sets. Consumed by map v3.

### Ingest filters
Gates on `ytk add` (and everything that calls it, including the inbox
ingest): duration bounds, captions requirement, and the interest_tags gate
described above. `--force` bypasses all of them.

### Misc
- **whisper model** — faster-whisper size for `ytk memo` and caption-less
  video fallback. base is fast; large is accurate but slow on 16G.
- **github repos** — repos offered when `ytk triage` / memo routing files
  issues.
- **memo notify** — where memo confirmations land; none checked =
  focus-aware auto.

## Example setups

### 1. "Capture everything, curate later" (current default)
- filters.interest_tags: empty — nothing rejected at ingest
- hub.tags: a handful of intent chips (build-idea, reference, movies...)
- cadence: 15 min everywhere
- Workflow: skim /inbox, tap a chip + drop a thought on the good ones.
  The thought is what feeds the explicit interest channel — tags alone
  don't carry r >= 2 signal.

### 2. "Strict diet" — only technical content enters the vault
- filters.interest_tags: [ai, dev-tools, geospatial, creative-coding, go]
- filters.min_duration: 120 — no shorts
- filters.require_captions: true
- Cost: enrichment runs before the gate (the tags come from it), so
  rejected videos still spend a Haiku call. Gate saves vault noise, not
  API spend. Use `ytk add --force` for one-off exceptions.

### 3. "Instagram-heavy, quiet YouTube"
- cadence: instagram 10, youtube 120, pinterest 240
- interest.content_sources: instagram + web only — TikTok saved but kept
  out of the taste profile
- hub.tags trimmed to the 3-4 chips you actually tap on reels.

## Where things live

| What | Where |
|---|---|
| this config | ~/.ytk/config.yaml |
| tag merge decisions | ~/.ytk/tag-aliases.yaml |
| queue + per-source pull times | ~/.ytk/reels_state.json |
| daemon logs | ~/.ytk/logs/hub.log |
| interest profile output | vault: second-brain/me/profile.md |
