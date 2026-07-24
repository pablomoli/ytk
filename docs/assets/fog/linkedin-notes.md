# Post material — the knowledge-map math series

Working notes for a future LinkedIn post / blog. Figures 01-06 in this
folder tell the story in order; quotables and numbers below.

## The paragraph (filament tracing, keep verbatim)

> The strand comes out ordered, uniformly spaced, and continuous by
> construction — strand-y because it literally is one. Each traced strand
> then claims the nearby crest points so we don't trace it twice, and
> per-vertex density lets strands taper where the fog thins.

Context: replacing nearest-neighbor chaining of converged SCMS walkers
(gaps render as dashes) with predictor-corrector ridge tracing — step
along the ridge tangent (top Hessian eigenvector), snap back onto the
crest with sideways-only mean-shift iterations. Same method astronomers
use to trace the cosmic web through galaxy surveys. Figure 05 is the
before/after: 31 fragments (median 8 vertices) -> long tapered strands
(median 52, longest ~100).

## The distance idea (reader-suggested beat: measure your own map)

Asked mid-build: "is it possible to compute the distance between the
notes and the strand? would that be something cool to plot?" — which is
independently the published methodology: astronomy characterizes
galaxies by distance-to-nearest-filament.

Result (figure 06): median note sits 0.55 bandwidths from its nearest
strand; 98.8% of 4,460 notes lie within 2h of a 274-vertex skeleton — a
16x compression of the map that loses almost nobody. Per-domain medians
rank territories from highway-hugging (usf 0.21h, hacklytics 0.29h) to
sprawling (epicmap 0.69h — the biggest, most alive territory sprawls
widest around its highway). The far tail = frontier notes no highway
reaches.

## Story beats / one-liners

- Your knowledge base rendered like the universe: notes as galaxies,
  interests as filaments, gaps as voids.
- Every formula hand-derived and checked against finite differences —
  the math minor doing production work.
- The matplotlib witness: an independent renderer that caught two
  display-normalization bugs and one dedupe bug before anything shipped.
  Never trust only the renderer you also wrote.
- Scale-space lesson (figure 04): adaptive bandwidth sharpened the fog
  and shattered the filaments — the estimator must match the question
  (fog = local, web = connectivity).
- Cardano's 16th-century cubic formula computes the eigenstructure of a
  2026 knowledge graph's density field. Old math doesn't expire.
- Shells (figure 09): swap the slider's >= for an absolute value and the
  fog becomes an onion — |f - c| < eps is the poor man's isosurface, the
  Monte-Carlo preview of marching cubes. Thickness isn't constant: a band
  of width 2eps in density is a slab of width 2eps/|grad f| in space, so
  shells hug steep peaks and puff out over flat saddles (the coarea
  formula, visible to the naked eye).

## Session snapshot — 2026-07-24 (for the report's closing chapters)

Two sessions ran in parallel this night; both feed the report.

**Main session (map features + planning):**
- Progressive-clustering orbs removed (6ceee76) — they were a placeholder
  for the junction-anchored planets (#78) and hid points at overview zoom.
  Deleting them also deleted a per-frame O(n) allocation and mooted half of
  the perf issue (#101, trimmed accordingly).
- Shell-band fog mode shipped (4255078): a `shell` chip swaps the slider
  from superlevel set to thickened level set |den - level| < 0.06 — the
  Monte-Carlo preview of marching cubes (#100). Asset 09 is its witness;
  eps was measured there before the shader hardcoded it. Report beat: band
  thickness ~ 2eps/|grad f| (coarea formula, visible to the naked eye).
- Map controls moved off the header into an on-canvas widget (8b94ceb).
- Planning: epic #107 (typing gate -> shader arc A-G -> volume -> WebGPU);
  #106 semantic domains — the everything view's grouping axis was
  provenance (path slugs) for 92% of points while positions were semantic;
  content collapsed to 2 buckets. Fix: grove buckets become the map's
  domain axis, gated on #105 (descriptions -> one batched re-embed).
- Discovery for the debug-stories chapter: grove_buckets.yaml's theme
  matchers were ALL stale — a profile re-synthesis renamed every theme and
  nothing noticed. Direction set: centralize theme state (stable IDs, one
  loader, builds fail loudly on stale references — detail on #106).
- Meta-beat worth keeping: the user spotted the semantic-vs-label mismatch
  himself, by eye, before any analysis — the intuition the series is
  supposed to build, demonstrably building.

**Graph-tidying session (parallel, flow-pulses worktree — shipped):**
- `scripts/plot_assets.py` now regenerates **all nine** figures (09
  included, so no separate `plot_fog.py --shell` pass is needed) from the
  live map payload under one house style, replacing nine ad-hoc heredocs.
  `--only N` for a single figure, `--refresh` to recompute the cached
  historical geometry (`~/.ytk/fog-assets-cache.json`).
- The dead space had a specific cause worth keeping for the report: every
  panel hardcoded `(-1, 1)` limits while the embedding spans x -1.2..0.8,
  y -0.8..0.7 — the data drew itself into a corner and matplotlib's
  default 3D margin ate the rest. Fix: cube limits centred on the data
  plus `set_box_aspect(zoom=)`. A *proportional* box aspect looks like the
  obvious fix and is a trap — matplotlib shrinks the axes to satisfy it,
  which mattes the sides and reintroduces the gap; the figure must instead
  be proportioned so square cells fit.
- Text clipping (06): titles wrapped, gutters widened, the colourbar moved
  underneath the 3D panel where it had been colliding with the domain
  names, and bar-axis headroom so the longest bar clears its frame.
- Also: frames on every panel + figure, magma with chroma +35% and a gamma
  lift (the fog's median density is 0.17, near-black on the raw ramp),
  dpi 110 -> 200 (figures now 2300-3300px wide).
- `trace_filaments` gained `dedupe=False` so figure 07's pre-trim skeleton
  stays reproducible rather than being lost history — the forensic
  comparison regenerates instead of depending on a vanished snapshot.

## Figure index

01 uniform fog panels (first cloud + threshold sweep)
02 uniform vs adaptive bandwidth fog
03 adaptive fog final (after display-normalization fix)
04 filaments: uniform vs adaptive bandwidth (the scale-space verdict)
05 filaments: chained vs traced (dashes -> strands)
06 note-to-strand distance (histogram, frontier map, per-domain ranking)
07 trim forensics (old vs new skeleton: same coverage, 40% less ink)
08 junctions (the crossroads: endpoint-on-trunk detection + gold beacons)
09 shell-band (fill vs shell, onion nesting, cross-section rings)
