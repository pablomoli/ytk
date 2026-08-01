# /orb — semantic sphere gallery

Date: 2026-08-01
Status: awaiting review
Origin: DesignCourse "Claude Fable 5 UI/UX One-Shots" test 2 (vault:
`sources/youtube/claude-fable-5-uiux-one-shots-5-tests.md`), adapted from a
one-shot prompt into a spec. Reference site: https://www.phantom.land/

## Brief

The source prompt, recovered from the video frame (not in the vault note —
Gary never read it aloud):

> This is a screenshot from: https://www.phantom.land/ — I want you to use
> GSAP and Three.js to recreate a similar experience where the gallery is in
> a spherical dimension, similar to the screenshot. It's as if you're inside
> of a sphere, and you're looking at a gallery. You should be able to left
> click and drag around with some lenis smooth scroll-style easing. When you
> tap on a card, it should animate a new page in, but you don't have to go
> beyond a basic template for that page. Our focus is on the gallery itself.
> Feel free to use any image asset, and style it as similar as possible and
> also make it function as similar as possible. Use chrome devtools to
> ensure you nail it.

Adaptation: the cards are the ytk library (566 notes, ~90% with thumbnails),
and tile placement is semantic — position on the sphere comes from the
existing content embedding layout, so neighbours are related content. The
"new page" is the existing `NoteViewer`, not a template.

## Decisions (already made)

- Built to repo conventions, not one-shotted: scene module under `web/src/lib/`,
  resource ownership per `docs/architecture/map-renderer-decomposition.md`.
- New standalone route `/orb`. `/library` and `/map` untouched.
- Contents: the 505 content-view points (`c3`/`th` carriers in `map.json`),
  joined to library notes by vault path. No pagination; the sphere holds the
  full content set.
- Sphere layout chosen by measurement among three candidates (below), all
  three shipped in `map.json` so the route can flip between them at runtime.
- Full interaction: drag + inertia, tile-zoom on click, `NoteViewer` handoff.

## Reference observations (phantom.land, recorded 2026-08-01)

Measured headless with a rAF sampler; DOM tween values read from GSAP inline
styles mid-flight.

- Gallery: inside-of-a-sphere tile wall, drag to look, tiles carry
  contact-sheet marginalia (year, tags, caption). DOM anchors exist but the
  canvas raycasts clicks; the anchors are not the interaction path.
- Forward transition, tap → project page:
  1. WebGL phase, ~0.5s eased: camera dollies into the clicked tile, canvas
     only, no DOM change. (Duration approximate: the recorder's clock
     patch provably dilated the DOM tweens but its effect on the WebGL
     phase could not be isolated; the video demo shows the same order of
     magnitude.)
  2. Hard swap in one frame: canvas unmounts, page DOM mounts.
  3. Staggered DOM entrance: title split-lines rise from translateY(40px)
     with opacity; separator rules draw scaleX(0→1); hero fades up;
     below-fold blocks start at opacity:0/translateY(10px) and reveal on
     scroll.
- Close (X): hard cut. Route swap at t=33ms, gallery restored by t=58ms, no
  reverse animation.

Where we deviate deliberately: our close reverses the open (NoteViewer
already animates back to its origin rect); phantom's cut is the weaker half
of their own transition and costs us nothing to beat.

## 1. Layout computation — `scripts/build_map.py`

New function producing three arrays of unit vectors over the 505 content
points, written to `map.json` as
`content.sphere = {radial, haversine, lattice, scores, chosen}` (~50 KB):

- **radial** — `c3` minus centroid, normalized. Direction kept, radius
  discarded.
- **haversine** — `project(cvecs, nn, md, dims=2, output_metric="haversine")`
  → (lat, lon) → unit xyz. Reuses the content view's fitted `n_neighbors`/
  `min_dist` and `random_state=42`.
- **lattice** — Fibonacci sphere of N points; slots assigned theme-block
  first (17 themes as contiguous runs along the lattice's spiral order,
  runs sequenced by greedy nearest-neighbour walk over theme centroid
  directions from the radial layout), within a theme by angular order from
  the radial direction.

Scoring, two axes per layout, stamped into `scores`:

- Fidelity: `sklearn.manifold.trustworthiness(cvecs, unit_xyz,
  n_neighbors=15, metric="cosine")` — the metric already stamped as
  `trustworthiness_3d`, so sphere numbers are comparable to the record.
- Legibility: mean angular nearest-neighbour distance, and the count of
  pairs closer than one tile's angular radius (~4.2° at 505 tiles) — i.e.
  physically overlapping tiles.

`chosen` = best fidelity among layouts whose overlap count is within an
acceptance bound (no more than 5% of tiles overlapping); the route defaults
to `chosen` but can render any of the three. Keeping the losers in the
artifact is deliberate: the scores say which preserved neighbourhoods, only
looking says which is worth inhabiting, and a disagreement between those is
a finding, not a bug.

Risk, stated plainly: `output_metric="haversine"` is the least-exercised
UMAP path here. Verified first, before any renderer work, on the real 505
vectors. If it fails to converge or clumps pathologically, the measurement
records that and `chosen` falls to lattice or radial honestly.

Also added while in the file: content points gain a `thumb` field (rel path
from the existing `thumbs` dict at build time) — `img: bool` alone cannot
feed a texture atlas.

## 2. Delivery — `GET /api/orb`

Thin endpoint in `ytk/ui/server.py`: reads `map.json`, returns only content
points and the sphere block, fields `{p, t, c, u, d, th, thumb}` + layouts +
scores (~60 KB vs the full 1.9 MB). No projection logic server-side; it
serves precomputed coordinates. Client API wrapper `web/src/api/orb.ts`
follows `map.ts` conventions (typed, `useQuery`).

## 3. Renderer — `web/src/lib/orb/`

Module layout and ownership per the map-renderer decomposition doc; every
GPU resource has one owner with a `dispose()`.

- `atlas.ts` — one 4096² canvas-composited atlas, 128 px tiles, 32×32 =
  1024 slots (505 used). Thumbnails fetched from `/vault-media/<thumb>`,
  drawn cover-cropped. Upload once as a `CanvasTexture`. Until each image
  lands, its slot holds a theme-tinted placeholder (17 hues from the theme
  index) so the sphere renders complete on first paint and sharpens as
  images arrive. Failed loads keep the placeholder. Owner of the texture.
- `scene.ts` — camera at origin, fov 60. One `InstancedMesh` of 505
  inward-facing quads at radius 1, each oriented tangent to the sphere,
  per-instance atlas UV offset and a per-instance dim factor (used by the
  zoom). One draw call. Owner of geometry/material/renderer.
- `controls.ts` — pointer drag → yaw/pitch on the camera. Inertia: velocity
  from recent pointer deltas, critically-damped spring settle (the
  lenis-style easing named in the prompt — a dozen lines, no dependency).
  Pitch clamped to ±75° so the poles never flip. Wheel maps to yaw.
- `pick.ts` — raycast → instance id; also projects an instance's world
  quad to a screen-space `DOMRect` (needed for the NoteViewer handoff).

## 4. Route — `web/src/routes/orb.tsx`

Owns canvas lifecycle: create on mount, `dispose()` on unmount, resize via
`ResizeObserver`. Renders in-page controls (never in the nav bar): layout
switcher (chosen/radial/haversine/lattice, with each one's scores shown as
small print) and a theme filter that dims non-matching tiles.

Interaction spec, phantom-faithful where it earns it:

1. **Hover** — raycast under cursor; hovered tile scales to 1.06 and a
   caption (title, date) fades in near it as DOM overlay. Cursor becomes
   pointer.
2. **Click (not drag)** — a press that moves < 6 px. GSAP timeline, ~0.5s
   `power2.inOut`: camera yaw/pitch tween to center the tile + dolly along
   the tile's normal until it subtends ~60% of viewport height; all other
   instances' dim factor eases to 0.25.
3. **Handoff** — at the tween's end, `pick.ts` projects the tile quad to a
   screen rect, route opens `NoteViewer` with that as `originRect`.
   NoteViewer is unchanged; the sphere is just another origin-rect
   producer, exactly like `FreshCard`.
4. **Close** — NoteViewer's existing reverse animation runs; camera eases
   back to rest radius (~0.3s) and dim factors restore. No hard cut.
5. **Drag** — grab-and-throw with the spring settle. During drag, hover
   and click are suppressed.

## 5. Verification

Python (`tests/`): unit vectors are unit-norm and NaN-free; determinism
under `random_state=42`; lattice covers every theme contiguously; scores
present with both axes; `thumb` populated for every point whose url is in
the visual collection. The retrieval eval gate is untouched (no search-path
changes), but `build_map.py` changes mean a map rebuild before QA.

TypeScript (vitest, real Chromium per repo convention): atlas UV rect
correct for a known slot index; drag delta produces expected yaw/pitch and
the spring settles below tolerance; a synthetic pointer sequence
distinguishes click from drag at the 6 px threshold; a known world position
projects to the expected screen rect; route unmount calls every
`dispose()` (leak check via `renderer.info`).

No screenshot tests of the sphere; visual QA is by eye against the three
layouts.

## 6. Out of scope

- `/library`, `/map`, `NoteViewer` internals: untouched.
- No `lenis` dependency; no new `styles.css` rules (#136 — Tailwind +
  canvas only).
- No pagination/LRU texturing; the content set (505) fits one atlas. The
  design breaks at ~1024 content notes (atlas full) — noted here so the
  failure is anticipated, not silent.
- No entrance choreography beyond placeholder-to-image sharpening.
- Memory notes (4147 points) stay off the sphere; they have no thumbnails
  and would swamp the wall.
