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

## Figure index

01 uniform fog panels (first cloud + threshold sweep)
02 uniform vs adaptive bandwidth fog
03 adaptive fog final (after display-normalization fix)
04 filaments: uniform vs adaptive bandwidth (the scale-space verdict)
05 filaments: chained vs traced (dashes -> strands)
06 note-to-strand distance (histogram, frontier map, per-domain ranking)
