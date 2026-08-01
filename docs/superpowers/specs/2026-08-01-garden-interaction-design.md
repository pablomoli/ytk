# Garden interaction: picking, time scrub, seasons

Design for #153's interactive layer. Scope settled 2026-08-01: leaf-note
binding (prerequisite), picking with an in-scene panel, time scrub with
play, and freshness-as-season riding on the scrub. Prune and graft is
explicitly deferred (see final section) — the stage-then-commit sketch is
preserved there so the decision is not re-litigated from scratch.

The blocker named in #153 is identity: limbs map to real dendrogram
clusters, but twigs are invented texture and leaves are instanced geometry
with no note attached. Everything here either fixes that or builds on the
fix.

## 1. Leaf–note binding (prerequisite)

The pipeline already assigns notes to clusters; the missing hop is cluster
→ leaf site. When twigs are generated for a limb, the limb's notes are
assigned to twig endpoints deterministically: sorted by capture date,
mapped by stable hash onto available sites, so the same note lands on the
same twig across rebuilds — the same discipline as `hash(bucket) ^ seed`.

- Notes beyond available sites wrap: a site can carry more than one note
  (dense old clusters). The pick panel renders multi-note sites as a list.
- The binding is pipeline output, a parallel array `leafSites[i] →
  noteIds[]`, so the scene can bake ids into instance attributes without
  new geometry work.
- Nothing renders differently after this step; the canopy becomes
  addressable, not different.

## 2. Picking

Id-buffer picking, no raycasting against procedural geometry.

Two id spaces baked as instance attributes: limb segments carry cluster
id, leaf instances carry leaf-site index. On pointer-down, render one
offscreen id frame (color = id, no lighting), `readPixels` under the
cursor, resolve:

- leaf hit → note(s) at that site
- limb hit → cluster
- background → deselect

Hover uses the same buffer on throttled pointermove to drive a highlight
uniform: picked limb brightens, everything else dims slightly, at the
palette level against the observatory tokens.

An id-buffer read miss (antialiasing edge) resolves as background — never
a wrong note.

### Panel

Slides in from the right over the canvas, in-page (nav bar stays links
only, #136 policy).

- Leaf pick: title, date, thesis, key moments, tags, and an "open note"
  link out to the hub note view. Multi-note sites show a compact list
  first.
- Limb pick: bucket name, note count, date span, and the cluster's notes
  as a scrollable list. Each row is pickable and pulses its leaf in the
  scene, so panel and canopy stay pointing at each other.
- Escape or background click closes. Camera eases gently toward the
  picked limb — reframing, not teleporting.

Note content is fetched on pick from the existing note endpoint; the map
payload stays lean (the #68 lesson, not repeated here).

## 3. Time scrub + play

A horizontal scrub bar docked at the bottom of the garden page, in-page.

- The track is the capture-volume sparkline: a low area chart of
  notes-per-week, so busy stretches are visible terrain to aim for.
- Left of the track: play/pause. Right: displayed date, and a "now"
  button that snaps to the present in one gesture.
- Dragging sets T. The pipeline re-runs debounced (~45ms), so a fast drag
  samples history rather than grinding through it.
- Play advances T at a fixed pace: full history in roughly 60 seconds,
  auto-pausing at the end.
- When T < now, a thin desaturated border tints the viewport edge —
  unmistakably the past, no watermark over the scene.
- Picking works while scrubbed. The panel shows the note as it exists
  (content is not versioned), but the population is honestly as-of-T
  because the pipeline only saw notes ≤ T.

### Time model: recompute, not mask

The scrub position filters notes to capture date ≤ T and the parametric
pipeline re-runs in full — envelope, scaffold, girth, twigs measured from
the actual note population at T. Intermediate states are fully valid
rather than tween artifacts (#153's own argument). The incremental-attach
invariant (trees never reshuffle topology on rebuild) means the tree at T
is a genuine subtree of today's, so scrubbing is stable frame to frame.

Rejected: shader-side birth-date masking (limbs would exist at full girth
from frame one — the skeleton would not grow, only the foliage; the
replay would lie about structure). Fallback if recompute is slow: monthly
precomputed keyframes with masking inside a month — build only if the
measurement below demands it.

**Gate: measure full-vault pipeline time before building the scrub.** If
recompute exceeds ~50ms, adopt the keyframe fallback and record the
measurement here.

## 4. Seasons

Season is a per-cluster scalar, not a global: days since the cluster's
most recent note at T, normalized by `fresh_window_days`.

- Drives the leaf/palette layer only. Fresh clusters render new-growth
  green at full leaf density; aging clusters shift toward the mature
  palette; dormant clusters thin toward bare twigs.
- Geometry (trunk, limbs, girth) never changes with season. Structure is
  history; foliage is recency.
- During play this is where the replay earns its keep: attention arrives
  at a bucket, flourishes, goes quiet — independent of the bucket's size.

## 5. Data flow

`/api/garden` grows two fields per note: capture timestamp and note id.
Title/thesis stay behind the existing note endpoint, fetched on pick.

Failure modes:

- A note missing a capture timestamp falls back to file date and is
  counted in a console-visible tally. Silent coverage gaps are how
  freshness features lie (measured before: timestamp coverage is not
  recency).
- Id-buffer misses resolve as background (above).

## 6. Tests

- Binding determinism: same input → same site assignment.
- Id round-trip: bake → render → readPixels → same id.
- Season scalar edges: empty cluster, single-note cluster, all-dormant.
- Scrub monotonicity: T2 > T1 ⇒ note population at T2 is a superset of
  T1.

## Build order

1. Binding (pipeline output + baked attributes; invisible)
2. Pipeline perf measurement (the section-3 gate)
3. Picking + panel
4. Scrub + play
5. Seasons

## Deferred: prune and graft

Parked 2026-07-31 by explicit decision — wanted, not now.

The sketch to resume from: stage-then-commit. Drags accumulate as staged
changes (moved limbs ghosted; a tray lists operations in plain language).
One Apply writes `~/.ytk/garden_buckets.yaml`, with a reason per
campaign, matching the file header's proposed-measured-approved
discipline. Apply re-runs the matcher first and reports the note-count
delta per bucket ("this graft moves 41 notes; this split leaves `oracle`
with 3") — the measured leg folded into the commit moment. Cancel
discards the sketch for free. Rejected alternatives, with reasons:
direct-write-with-undo (a slip is indistinguishable from intent; no
moment where a reason can be captured), per-gesture proposal dialogs
(ceremony lands between gestures instead of per intent, killing the
sketching loop).
