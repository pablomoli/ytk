# Grove workshop — design

2026-07-12. A new `/grove` route: an artsy, procedural depiction of the vault as a
field of growing trees, built as a workshop — the page where tree ideas are
developed and iterated, not a finished feature.

## Motivation

The /map route, even after the domain-hierarchy work, has no job beyond looking
around — so make the looking worth it. Reference: Marius Ballot, "Procedural 3D
Data Trees in Three.js" (enriched note:
`sources/youtube/procedural-3d-data-trees-in-three-js-a-shader-geometry-breakdown.md`).
The vault is literally a tree (vault -> domains -> subtopics -> notes with dates);
Ballot's pipeline renders trees organically. Decision from brainstorming: grove
metaphor (one tree per domain), new route coexisting with /map (migration
deferred), prototype-first, and — the user's framing — the grove is where we MAKE
the trees: start from the video's algorithm verbatim, iterate on top.

## Shape

**Route:** `/grove` in the hub SPA, lazy-loaded so the three.js dependency stays
out of the other routes' bundle. Marked experimental; /map untouched.

**Tech:** three.js for this route (tube geometry, lines, OrbitControls are free
there; judging looks fast beats bundle purity). Whether the winning look ports to
the raw renderer or /grove keeps three is decided later, in the real spec that
follows the workshop phase.

**Stage 1 — Ballot's algorithm, faithful, data-free.** Reproduce the video's
pipeline from the enrichment before binding any vault data:
- Node tree by BFS: node = {position, weight, depth}; 1-4 initial children
  sphere-distributed around the root; each child placed by scaling the
  root-to-node direction by a random scalar plus a noise vector; stop past a
  distance threshold from the root. Weight decays toward tips (branch girth).
- Segment decomposition -> centripetal Catmull-Rom smoothing -> per-point
  tangent/normal/binormal frames (neighbor directions + cross products) ->
  vertex rings sized by weight -> hand-stitched index buffer (ring pairs as
  quads), exactly the video's indexed-geometry walkthrough.
- Depth attribute backpropagated and normalized 0-1 per tree.
- Shading: fresnel edge glow (camera-space normal dot view); growth via the
  clamped-cosine ramp (progress uniform, depth as phase) scaling vertices along
  normals and gating fragment alpha; uTime sine pulse traveling by depth.

**Stage 2 — bind the vault.** BFS shaped by real data from `/api/map` (v2):
one tree per domain, planted where its UMAP centroid projects onto the ground
plane (scaled apart); one limb per subtopic, girth from note count; notes as
buds along their subtopic's limb ordered by date; domains without subtopics
grow saplings. Grove grows in vault-chronological order on load. Hovering a bud
names its note (the one function kept).

**Stage 3 — look variations,** toggleable on the same scene/data/camera:
1. wireframe skeletons (GL_LINES + bud points),
2. solid tubes (full Ballot),
3. particle foliage (tubes for structure, note-clusters as leaf masses).

**Workshop affordances:** a compact control panel — regenerate (seed), growth
replay, look switcher, and the generation knobs (initial children, noise
amplitude, distance threshold, girth decay, smoothing density, growth speed).
Params persist to localStorage. This panel is the point: the grove is where
trees are designed by turning knobs and looking.

## Out of scope (workshop phase)

Replacing /map, mobile, search/deep-link integration, porting to the raw WebGL
renderer, and any backend change. When a look wins, it gets its own spec and the
usual plan pipeline, built in slow visible stages (tree -> lines -> tubes ->
shading -> growth) per the video's structure.

## Success criteria

The user can open /grove, watch the vault grow as a grove, toggle three looks,
turn generation knobs and regenerate, and after living with it pick a direction
worth speccing for real.
