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

## 0. Data plumbing (the real prerequisite)

Verified against the code 2026-08-01: note→cluster membership exists only
server-side. `dendro.py` persists a `members` map (vault path → node id)
in `~/.ytk/grove/*.tree.json`, and `/api/garden` deliberately strips it
(`server.py:853` — "member maps are attach-time machinery... stay
server-side"). No note-level data — ids, paths, or dates — reaches the
client today, and no capture date is persisted per member anywhere:
`dendro.py` reads `meta["date"]` transiently for the stability calc and
discards it.

So before any binding:

- `dendro.py` records a capture date per member at attach time
  (frontmatter `date:`, file date fallback, fallback counted in the
  snapshot so coverage is visible — timestamp coverage is not recency).
- A new `/api/garden/members` endpoint serves `{path, date, node_id}`
  per bucket, keeping the topology payload lean (#68 discipline) —
  fetched once alongside the topology.
- The member key is the vault path, which is already exactly what
  `GET /api/note?path=` accepts (`server.py:83`). No new id scheme.

Existing snapshots have no member dates; a one-shot backfill from
frontmatter stamps them, with the fallback tally reported.

## 1. Leaf–note binding

With members and dates client-side, the missing hop is cluster → leaf
site. `buildTreeGeometry` already emits a concrete `leafSites` array
(`tree.ts:294`), but its cardinality is a byproduct of spine-sampling
density and the scene's instance budget (`scene.ts:408` subsamples by
stride) — unrelated to note count in either direction.

- Binding is deterministic: a cluster's notes sorted by capture date,
  mapped by stable hash onto that cluster's sites — same note, same twig
  across rebuilds, the `hash(bucket) ^ seed` discipline.
- Sites ≫ notes (sparse clusters): unbound sites render as ordinary
  foliage but resolve as background on pick — decorative, not lying.
- Notes ≫ sites (dense old clusters): sites carry lists; the pick panel
  renders multi-note sites as a list.
- Nothing renders differently after this step; the canopy becomes
  addressable, not different.

## 2. Picking

Id-buffer picking, no raycasting against procedural geometry.

Two id spaces, baked differently because the meshes differ (verified in
`scene.ts`): leaves are a real `InstancedMesh`, so the leaf-site index is
an `InstancedBufferAttribute` — direct extension of the existing
`iDepth`/`iPhase` pattern (`scene.ts:448`). Limbs are one merged
`BufferGeometry` per tree, so the cluster id is a per-vertex attribute —
same precedent as the existing `depth` vertex attribute. Both cheap;
neither is "one mechanism."

On pointer-down, render one offscreen id frame (color = id, no
lighting), `readPixels` under the cursor, resolve:

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
  picked limb — reframing, not teleporting. This is net-new machinery:
  `scene.ts` currently snaps the camera on `plant()` and otherwise
  leaves motion to OrbitControls damping; picking adds a small
  target-interpolation state (ease camera target over ~600ms, cancelled
  by any user orbit input).
- The panel itself is also new motion work: `.garden-panel` precedents a
  right-docked panel, but it toggles visibility; no slide-in drawer
  primitive exists in `components/ui/` (dialog and popover only). Build
  the slide as a plain transform transition on the existing panel
  pattern, not a new Radix dependency.

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

The scrub position filters members to capture date ≤ T, derives the
as-of-T topology, and the TS pipeline regrows in full — envelope,
scaffold, girth, twigs measured from the actual note population at T.
Intermediate states are fully valid rather than tween artifacts (#153's
own argument).

Corrected premise (fact-checked 2026-08-01): the incremental-attach
invariant in `dendro.py` guarantees forward growth never reshuffles
existing nodes, but today's snapshots carry no per-member dates, so
"the tree as of T" is not reconstructible from existing data — section
0's date plumbing is what makes it possible. With dates present, the
as-of-T tree is derived client-side: drop members newer than T,
recompute each node's mass from its surviving members, drop nodes whose
mass reaches zero. Because attach never restructures, the result is a
genuine subtree of today's topology — stability frame to frame comes
from that derivation, not from re-clustering.

Rejected: shader-side birth-date masking (limbs would exist at full girth
from frame one — the skeleton would not grow, only the foliage; the
replay would lie about structure). Fallback if recompute is slow: monthly
precomputed keyframes with masking inside a month — build only if the
measurement below demands it.

**Gate: measure filter-then-regrow time on the full vault before
building the scrub UI.** The measurement is only meaningful after
section 0 lands (it must include the member filter and mass recompute,
not just `growGardenTree` on today's topology). If a scrub tick exceeds
~50ms, adopt the keyframe fallback and record the measurement here. The
topology and members are fetched once on mount (`garden.tsx` pattern),
so a tick is pure client math — no network in the loop.

## 4. Seasons

Season is a per-cluster scalar, not a global: days since the cluster's
most recent note at T, normalized by a freshness window.

The window borrows the `fresh_window_days` *name* from the
interest-profile config (`ytk/config.py:49`), but that field belongs to
profile synthesis, not the garden. Decision: the garden gets its own
knob in the existing garden params, defaulting to the interest-profile
value so the two stay aligned unless deliberately split. Reusing the
other subsystem's semantics is a choice made here, not an assumption.

- Drives the leaf/palette layer only. Fresh clusters render new-growth
  green at full leaf density; aging clusters shift toward the mature
  palette; dormant clusters thin toward bare twigs.
- Geometry (trunk, limbs, girth) never changes with season. Structure is
  history; foliage is recency.
- During play this is where the replay earns its keep: attention arrives
  at a bucket, flourishes, goes quiet — independent of the bucket's size.

## 5. Data flow

Section 0 defines the plumbing: per-member dates persisted by
`dendro.py`, served by `/api/garden/members`, keyed by vault path. On
pick, the panel fetches `GET /api/note?path=` (`server.py:83`) and
parses frontmatter/thesis client-side via the existing `parseNote` path
that `NoteViewer.tsx` already uses.

Failure modes:

- A note missing a capture timestamp falls back to file date and is
  counted in a tally persisted in the snapshot and surfaced in the
  console. Silent coverage gaps are how freshness features lie (measured
  before: timestamp coverage is not recency).
- Id-buffer misses resolve as background (above).
- A member path that no longer resolves (note moved/deleted since the
  snapshot) shows a "note missing — reindex" row in the panel rather
  than an empty pane.

## 6. Tests

- Binding determinism: same input → same site assignment.
- Binding cardinality: sites ≫ notes leaves unbound sites picking as
  background; notes ≫ sites wraps without loss.
- Subtree derivation: as-of-T topology is a subtree of today's; node
  masses equal surviving-member counts; T = now reproduces the full
  tree exactly.
- Id round-trip: bake → render → readPixels → same id.
- Season scalar edges: empty cluster, single-note cluster, all-dormant.
- Scrub monotonicity: T2 > T1 ⇒ note population at T2 is a superset of
  T1.
- Date fallback tally: a fixture with missing frontmatter dates reports
  the exact fallback count.

## Build order

1. Data plumbing (section 0: member dates in dendro.py + backfill +
   `/api/garden/members`)
2. Binding (client-side site assignment + baked attributes; invisible)
3. Filter-then-regrow perf measurement (the section-3 gate)
4. Picking + panel
5. Scrub + play
6. Seasons

Steps 1–2 are pure infrastructure with no visible change; the first
user-visible payoff is step 4. That is deliberate — #153 names identity
as the blocker, and both interactive features are hostage to it.

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
