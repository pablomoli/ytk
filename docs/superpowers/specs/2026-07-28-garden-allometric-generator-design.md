# Garden: allometric, up-and-out, fractal-filled trees

Date: 2026-07-28
Supersedes the generator described in `2026-07-12-grove-workshop-design.md`.
Keeps the shader/material work from `2026-07-14-grove-shader-decoration-design.md`.

## Problem

Three complaints against the current `/grove`, each with a distinct cause in code.

**Width ignores height.** Girth is decided top-down. Root weight is always 1,
each BFS step multiplies by `girthDecay` (`tree.ts:208`, `datatree.ts:99`), and
ring radius is `weight * params.girth`. The trunk's width is therefore fixed
before the generator knows what the trunk will carry. In data mode a two-note
bucket still receives at least half a large bucket's girth, because
`sizeScale = 0.45 + 0.55*sqrt(n_notes/max)` (`scene.ts:258`). A seedling and a
mature tree look like the same trunk at different scales.

**Growth goes up, not up and out.** Three compounding causes. `upBias` is
re-added at every step regardless of branch order (`tree.ts:184`,
`datatree.ts:82`), so a limb that forks laterally is immediately re-aimed
vertical. `reach` is a sphere around the origin (`tree.ts:204`), so the crown
is a dome with no lateral budget. And the fork's `polar` splay
(`datatree.ts:130`) is undone by the very next step's up-pull.

**No fractal structure.** There is no recursion below the dendrogram. A bucket's
cluster hierarchy is a few levels deep, `stepsFor` yields 3-12 steps per limb,
and below that there is nothing but instanced leaf cards. Nothing makes a twig
resemble a smaller branch.

## Decisions taken

Recorded because they constrain everything below.

- Target silhouette: **broad deciduous crown** (oak-like) at maturity.
- Girth is computed **bottom-up from what a limb carries**, not top-down.
- When measured data and fractal form conflict, **data wins and fractal fills
  the gaps**: the dendrogram remains authoritative for trunk and major limbs;
  generated structure only appears below the measured clusters.
- The feature is renamed **grove -> garden**, fully (code, routes, API, tests).
- The cells/organelles/being idea belongs to the **growth** page and is out of
  scope here. It gets its own spec.

## Architecture

Five stages replacing the current `generateTree` / `generateDataTree` split.
Stages 0-3 are pure functions with no WebGL or Three.js scene dependency, each
in its own module under `web/src/lib/garden/`. Stage 4 is the existing geometry
builder, unchanged in behaviour.

### Stage 0 - envelope (`envelope.ts`)

Each bucket gets a crown envelope: an oblate ellipsoid of height `H` and
horizontal radius `R`.

- `H` scales with bucket note count (sub-linear; log or sqrt, tuned against the
  real bucket distribution so the largest bucket does not dwarf the frame).
- `R/H` is **not constant**. It ramps from roughly 0.35 for the smallest bucket
  to roughly 1.1 for the largest.

The ramp is the point. Juvenile trees really are narrow and vertical; crown
spread lags height. Without it a seedling is a scaled-down oak, which is the
shape complaint in miniature.

All later stages grow inside this envelope, so "wider than tall at maturity" is
a parameter rather than an emergent accident.

The envelope is **per bucket, derived from that bucket's data**. This is load
bearing: after stage 3, trunk width is a function of how many twigs a tree
carries, so a seedling can only be thinner than a giant if their twig counts
genuinely differ, which requires per-bucket envelopes and attractor budgets. A
shared garden-wide envelope would reintroduce the equal-width problem.

### Stage 1 - scaffold (`scaffold.ts`)

The dendrogram builds trunk and major limbs, as today, with four changes.

**Gravitropism becomes a gradient by branch order.** Replace the constant
`upBias` with `upPull = upBias * pow(orderDecay, order)`: the trunk is strongly
vertical, first-order limbs pull up substantially less, second-order and beyond
are nearly horizontal (plagiotropic). This is the single change that most
directly produces the up-and-out reading.

**Limbs aim at their lobe of the envelope**, not at "outward plus up". Each
dendrogram child owns an angular sector (golden-angle azimuth, as today) and a
radial target proportional to its share of note mass. `reach` becomes an
ellipsoid containment test instead of a sphere.

**Gravity sag on old limbs.** A second tropism axis, perpendicular to the
first: the order gradient runs trunk-to-twig, this one runs low-to-high. Older,
lower, longer limbs are pulled downward under their own weight while young
upper limbs angle toward the sky. Apply as a downward term scaled by limb
length and by inverse height within the envelope, composed with — not replacing
— the order gradient.

The two axes together are what separate a tree silhouette from a shrub: lower
limbs reaching out and drooping, crown reaching up. Source:
`sources/youtube/why-i-stopped-using-tree-assets-in-my-game.md`, where the
first model failed on exactly this and the fix came from pine biology rather
than from any tool feature.

Constraint: sag fights the hemisphere fold that keeps canopy above ground. The
downward pull needs a floor, or a long low limb gets driven through the ground
plane and folded back, which reads as a kink rather than a droop.

The floor must be a soft asymptote, not a clamp. Measured in
`docs/assets/14-garden-allometry/03-tropism-axes.png`: clamping position after
the fact (`y = max(y, sagFloor)`) makes the lowest limbs arc down, hit the
floor and then run dead flat along it, which reads as clipping against an
invisible wall. Attenuate the sag term as `y` approaches `sagFloor` so the limb
eases into a shallow curve instead. A hard clamp stays only as a safety net
that should never fire. Note that a test asserting `y >= sagFloor` passes for
the clamped version too and will not catch this.

**Branch length falls with height.** Lower limbs are longest, shortening toward
the apex. Cluster persistence still ranks limb length — data stays
authoritative — but a height-derived multiplier scales it, so the crown tapers
instead of carrying full-length limbs to the apex.

Retained from the current generator: `stiffness` blending of direction, the
noise vector, and the hemisphere fold that keeps canopy above ground.

### Stage 2 - twigs (`twigs.ts`)

Space colonization (Runions et al. 2007) below the measured clusters.

For each leaf cluster of the dendrogram, scatter attractor points into that
cluster's lobe of the envelope, count proportional to its note count. Then the
standard loop: each attractor within attraction distance `di` of a branch tip
associates with the nearest tip; each tip with associated attractors grows one
step of length `D` toward the normalised average direction of its attractors;
attractors within kill distance `dk` of any tip are removed. Iterate until no
tip grows or the node budget is exhausted.

Suggested starting values, to be tuned: `dk` about `2*D`, `di` about `8*D` to
`16*D`.

Because attractors are consumed as branches reach them, branches spread to fill
space instead of crowding, and the recursive-looking structure emerges from the
algorithm rather than from explicit fractal rules. This layer supplies the fine
structure the shallow dendrogram cannot.

### Stage 3 - girth (`girth.ts`)

One bottom-up (post-order) pass over the completed skeleton.

- Every tip gets the same tip radius `r_tip`.
- Every internal node gets `r = (sum over children of r_child^n)^(1/n)`.
- `n` is a knob, `pipeExponent`, defaulting to about 2.5. (`n = 2` is pure
  cross-section area preservation, the da Vinci rule; ~2.5 is the empirical
  fit for real trees.)

`girthDecay` and the `weight` field are removed entirely. The `girth` parameter
is redefined as a scale on `r_tip` rather than the trunk radius.

Consequence, and the fix for complaint one: trunk width emerges from the total
twig count the trunk supports. Height coupling is automatic and needs no
special case, because a taller tree carries more twigs.

### Stage 4 - geometry (existing)

`buildTreeGeometry` is unchanged in behaviour: chain decomposition,
centripetal Catmull-Rom spines, parallel-transport TNB frames, weight-sized
vertex rings, stitched quads, welded fork knuckles, apex tip caps, leaf sites.
It reads Murray radii where it previously read `weight * girth`.

## Data honesty

The scaffold is measured: cluster persistence sets limb length, mass sets lobe
share and attractor count. Twigs are generated texture *below* the resolution
of the measurement, and encode nothing beyond their cluster's note count. The
existing aesthetic/data toggle stays, so a purely decorative tree remains
available.

## Rename: grove -> garden

Full rename, one coherent commit, no behaviour change:

- `web/src/lib/grove/` -> `web/src/lib/garden/`
- `web/src/routes/grove.tsx` -> `garden.tsx`; route `/grove` -> `/garden`; nav
  label; regenerate `routeTree.gen.ts`
- `GroveParams` -> `GardenParams`, `mountGrove` -> `mountGarden`, `GroveLook` ->
  `GardenLook`, `GrovePayload` -> `GardenPayload`, and the rest in kind
- `/api/grove` -> `/api/garden` in `ytk/ui/server.py` and the client fetch
- `tests/test_grove_*.py` -> `tests/test_garden_*.py`
- `scripts/grove_lab/` -> `scripts/garden_lab/`
- `docs/grove-lab/` -> `docs/garden-lab/`

**User config is not renamed silently.** `~/.ytk/grove_buckets.yaml` lives on
the user's disk. The loader reads `garden_buckets.yaml` first and falls back to
`grove_buckets.yaml`, so an existing file keeps working. Do not move or rewrite
the user's file.

## Budgets

Current budgets are far too low for this design: `MAX_NODES` is 2200 and the
scene shares `4400/treeCount` across trees. Space colonization needs
substantially more headroom to read as fine structure.

The target is several thousand nodes for a large tree, scaled down as tree
count rises. **This number is a guess.** Space colonization plus this geometry
has not been measured at that scale on this machine (M3, 16GB). Treat the
first performance checkpoint as the thing that sets the budget, not this
paragraph.

## Verification

Stages 0-3 are pure functions and unit-test directly, no WebGL required
(vitest, in real Chromium per project convention).

Invariants to pin:

1. **Allometry** - given equal `r_tip`, a taller tree has a thicker trunk.
2. **Murray** - at every internal node, `r^n` equals the sum of children's
   `r_child^n`, within tolerance.
3. **Containment** - every generated node lies inside its bucket's envelope.
4. **Determinism** - identical seed plus identical topology yields an identical
   skeleton, node for node.

Invariant 4 also fixes a live defect: `plant()` currently draws one shared RNG
stream for the whole garden (`scene.ts:225`), so one new note in one bucket
shifts every downstream draw and reshuffles every tree. Seeding each tree from
`hash(bucket) ^ seed` makes an unchanged bucket render identically across
snapshots.

**Ground-truth figure**, archived under `docs/assets/`: trunk radius plotted
against tree height across the real bucket size distribution, before and after.
This is the plot that decides whether the allometry works. It doubles as the
performance checkpoint (node counts and frame time recorded alongside).

## Risks

- **Budget guess.** Node counts above are untested at this scale on this
  hardware. The figure sets the real number.
- **Shallow dendrograms.** If a bucket's hierarchy is only two or three levels
  deep, the scaffold contributes little and nearly all visible structure comes
  from stage 2. The tree still looks right but encodes less measured structure
  than the current one does. Acceptable, but it should be observed rather than
  assumed.
- **Tuning surface.** Space colonization is sensitive to the `D`, `dk`, `di`
  ratios. Expect a tuning pass; the existing knobs panel is the right place to
  expose them during development.

## Out of scope

- Growth-page cells/organelles/being redesign (its own spec).
- Snapshot-diff growth animation and skeleton morphing (issue-level work
  derived from the RujiK research; noted, not built here).
- Any change to enrichment, retrieval, or the dendrogram computation itself in
  `scripts/garden_lab/dendro.py`.
