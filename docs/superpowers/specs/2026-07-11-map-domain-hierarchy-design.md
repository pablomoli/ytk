# Map domain hierarchy + focus growth — design

2026-07-11. Covers the `/map` route redesign: controlled domain-level grouping for the
everything view, hierarchical drill-down, selection/click bug fixes, and a shader
pass that makes focus transitions grow organically instead of flipping.

## Motivation

Three observed problems with the current map:

1. **Clicking a cluster selects a different one.** The canvas picker takes the nearest
   point within 12px, and cluster labels float 22px+ above their cluster over other
   clusters' points. Reproduced: clicking the blob under "Frontend Modal Components"
   selects "Map Marker Animation". Labels themselves are `pointer-events: none`, so
   clicking a label text does nothing. A precedence bug compounds it: with a group
   focused, hovering any other legend row dims every group (`focused && a || hovered && b`
   dims both the focused and the hovered group).
2. **The legend is unsorted.** Rows render in raw HDBSCAN cluster-index order while
   colors are assigned by size rank across the ramp, so the color sequence reads
   shuffled.
3. **Labels are uncontrolled and dominated by one project.** 2,037 of 4,532 points
   (45%) are epicmap session summaries; global HDBSCAN faithfully splits them into
   ~10 epicmap subtopics, so half the legend is epicmap. Project identity is already
   recoverable per point (session filenames encode it), so the top-level axis can be
   deterministic instead of emergent.

Reference for the transition aesthetic: Marius Ballot, "Procedural 3D Data Trees in
Three.js" (ingested: `sources/youtube/procedural-3d-data-trees-in-three-js-a-shader-geometry-breakdown.md`).
All animation is attribute + uniform driven — a normalized depth attribute phases a
clamped-cosine ramp so the mesh grows in staggered waves. Same architecture as our
morph shader; we adopt the technique for focus transitions.

## Decisions made

- Grouping approach: **domain → subtopic hierarchy** (not flat domains, not label
  discipline only).
- Content notes group by **interest-profile themes** at the top level, beside project
  domains.
- Legend sorted by **size descending** (matches color ramp rank).
- Canvas topic labels become **clickable** and focus their own group.
- Renderer stays **hand-rolled WebGL1**. r3f/three rejected: ~270 KB gzip to reproduce
  a 3 KB renderer, and the dual-layout morph + 2D/3D dim blend don't map onto three's
  camera/material model (recon report, 2026-07-11).
- Focus transitions animate as **growth reveals** (Ballot's phase-offset cosine ramp),
  which requires moving focus dimming out of baked vertex alphas into per-group
  uniforms — also removing the full buffer rebuild on every focus/hover change.

## Phase 1 — pipeline, hierarchy, fixes, core shader pass

### 1. Data pipeline (`scripts/build_map.py`)

**Domain assignment** — deterministic, no LLM, every point gets `dom`:

- claude-mem session summaries (`memories/claude-mem/summaries/summary-YYYY-MM-DD-{project}-{id}.md`):
  project parsed from filename via `summary-\d{4}-\d{2}-\d{2}-(.+?)-\d+\.md`.
- Memory atoms and project notes (`memories/{slug}/`, `projects/{slug}/`): folder slug,
  normalized — lowercase; strip `users-melocoton-developer-` / `users-melocoton-`
  prefixes; if the remainder starts with `{p}-` for a project `p` already above the
  domain threshold, collapse to `p` (folds worktree slugs like
  `epicmap-claude-worktrees-silly-shaw-fb5548` into `epicmap`).
- Content categories (youtube, instagram, tiktok, pinterest, web, screenshots):
  nearest interest-theme centroid, reusing `assign_themes` with the same
  25th-percentile confidence floor; below-floor points go to `other`.
- Remaining categories (memo, journal, vault) and any domain with fewer than 40
  points: merged into `other`.

**Subtopics — HDBSCAN per domain, not global.** For each domain with >= 120 points,
cluster its vectors (UMAP 15-dim reduction, `min_cluster_size = max(20, n // 50)`,
`min_samples = 10`). Smaller domains get no children. Within-domain noise keeps
`dom` and gets `g = -1`. Subtopic naming: c-TF-IDF scoped to the domain's documents,
then one batched Haiku polish call across all newly named subtopics (domain given as
context, existing labels passed as taken). Name anchoring (Jaccard >= 0.3 vs the
previous build's groups) is kept and stays global — on the first v2 build it will
re-adopt good v1 names like "County Layer GIS" for the matching epicmap subtopics.
Domains never touch Haiku; their names are the slugs / theme labels themselves.

**Schema v2** (`~/.ytk/map.json`):

```json
{
  "v": 2,
  "generated": "...",
  "content": { "params": {}, "groups": [] },
  "all": {
    "params": {},
    "domains": [{ "label": "epicmap", "n": 2037, "x": 0, "y": 0 }],
    "groups":  [{ "label": "County Layer GIS", "domain": 0, "n": 189,
                  "x": 0, "y": 0, "terms": "...", "weight": 0.04 }]
  },
  "points": [{ "...existing fields": 0, "g": 12, "dom": 0 }]
}
```

- `g` is the global subtopic index (or -1), `dom` the domain index (always set).
- UMAP layouts, the content view, and 2D/3D projections are unchanged. `--sweep`
  silhouette scoring switches from cluster labels to domain labels.
- The build warns if domains exceed 32 or subtopics exceed 96 (uniform array caps).

### 2. Renderer (`web/src/lib/mapRenderer.ts`, `mapAggregation.ts`)

**Uniform-driven focus (the enabler).** Today `alpha0/alpha1` bake the focus dim into
the vertex buffer, so every focus/hover change rebuilds all ~4.5k vertices and
transitions are instant flips. New model:

- Buffer gains per-point attributes: `dom` (float index), `phase` (normalized distance
  from the point to its subtopic centroid, domain centroid for within-domain noise —
  its growth phase), and a subtopic color
  set alongside the existing domain colors (blended by uniform, like the view morph).
- Vertex shader gains uniform arrays `domState[32]` and `subState[96]` (target alpha
  factors per domain/subtopic driven by focus + hover + hidden state) and a
  `focusProgress` uniform. Group visibility becomes
  `mix(currentAlpha, targetAlpha, ramp(focusProgress - phase))` — a clamped-cosine
  ramp per Ballot, so a newly focused domain blooms outward from its centroid while
  others recede in the same wave, staggered by `phase`.
- `setGroupFocus` / `setGroupHover` / `setHiddenGroups` stop setting `geometryDirty`;
  they retarget uniforms and restart `focusProgress`. Buffer rebuilds remain only for
  view and filter changes. (This also addresses the focus-change jank observed during
  the 2D/3D transition work.)

**Two-level focus semantics:**

- Overview: points colored by domain (ramp by domain size rank); canvas shows domain
  labels only; clicking a point, its domain's label, or a legend domain row focuses
  the domain.
- Domain focused: its points recolor by subtopic (uniform blend to the baked subtopic
  colors), its subtopic labels appear (top 10 by size), other domains dim. Clicking a
  point, subtopic label, or nested legend row narrows focus to that subtopic.
- Subtopic focused: single label, siblings dimmed, fly-to preserved.
- Click on empty canvas pops one level (subtopic -> domain -> none).
- Hover precedence fix: a hovered group temporarily takes the highlight; on leave the
  focused state is restored. Never dim both.

**Aggregation orbs** key on domain at overview, subtopic when the domain is focused
(`pointGroup` gains the focus level). Existing orb mechanics otherwise unchanged.

**Entrance animation — hard refresh only.** On a fresh document load, the map plays
an organic growth intro reusing the same machinery: an `introProgress` uniform sweeps
a clamped-cosine ramp against each point's `phase` (offset by its distance from the
map origin), scaling point size and alpha from zero — the graph grows outward from
the center, domains blooming in staggered waves, settling into the overview state
(~1.5s). It plays only on hard refresh: gate on a module-level "played" flag that
only resets with the document, so SPA navigations back to `/map` mount instantly.
A hash-focused deep link (`#d:...`) skips the intro rather than fighting it.

**Fragment/vertex garnish (all cheap, same shader):**

- Fresnel rim: brighten the sprite silhouette with `pow(1 - n.z, k)` using the fake
  sphere normal we already compute.
- Depth fog: mix point color toward the background with the existing `depth` value.
- Traveling pulse: `uTime` uniform + `phase` offset, a subtle sine wash gated to the
  focused domain. Twinkle on dust via hash-phase alpha jitter.

### 3. Route/UI (`web/src/routes/map.tsx`, `styles.css`, `api/map.ts`)

- Legend lists domains sorted by size descending; the focused domain's row expands to
  show its subtopics nested (also size-ordered). Alt-click hide works at both levels.
  Collapsed legend dots show domains.
- Canvas labels get `pointer-events: auto`, hover affordance, and click-to-focus.
- Tooltip shows `category · domain · subtopic` plus existing metadata.
- `api/map.ts` types gain `v`, `domains`, `dom`. If the payload lacks `v: 2`, render a
  dedicated state: "map data predates the domain hierarchy — run
  `uv run python scripts/build_map.py`". No compatibility shim.
- Focus state in the URL hash extends to `#d:{domain-label}` /
  `#d:{domain-label}:{subtopic-label}` (slugified labels, not indices, so links
  survive rebuilds) alongside the existing `#content` / `#2d` flags.

### 4. Testing

- Python (pytest): filename -> project parsing, slug normalization + worktree
  collapse, small-domain merge into `other`, theme-floor assignment, schema v2 emit
  (domain/subtopic counts, warning caps).
- TypeScript (vitest): legend sort helper, group-state resolution (focus/hover/hidden
  precedence — hovered overrides focused, never both dimmed), `pointGroup` by focus
  level, phase normalization.
- Playwright smoke, run in both 3D (default) and 2D (`#2d`): clicking a domain label
  focuses that domain (not a neighbor); legend order matches size rank; drill-down
  (domain -> subtopic -> pop via empty click); focus survives the 2D/3D toggle; the
  growth intro plays on a hard load, is skipped on SPA navigation back to `/map`,
  and is skipped when arriving on a `#d:` deep link.

### 5. Ops

After merge: `uv run python scripts/build_map.py` to regenerate `~/.ytk/map.json`,
then `uv tool install --reinstall .` so the hub bundle ships the new UI. The hub
serves the file as-is; no server changes.

## Phase 2 — follow-up (separate plan, not in scope now)

- Metaball orb merging: per-cluster quad with quintic smooth-min field summing
  sub-cell centers, so orbs merge as they condense (technique: iq's Shadertoy
  metaballs; reimplement, do not copy — CC BY-NC-SA default).
- Parallax nebula background: Star Nest-style starfield as a dimmed fullscreen quad
  in the same GL context, fed the camera uniforms (verify MIT header before lifting),
  or a `@paper-design/shaders-react` component (Apache-2.0) as a separate canvas layer.
- Stretch: render the focused domain's hierarchy as Catmull-Rom branch tubes from
  domain centroid to subtopic centroids with the growth ramp (the full Ballot "data
  tree" look). Medium-large; only if phase 1's growth feel earns it.

## Out of scope

Content view grouping, the 2D/3D morph mechanics, signal/recent filters, search/dive,
and the hub's other routes are unchanged.
