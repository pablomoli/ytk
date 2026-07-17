# Grove chromatic anatomy — shader decoration design

2026-07-14. Product/shader pass for `/grove`, following the data-native tree
work and E7 readback. This pass is allowed because the grove is promising as a
personal representation; it does not imply that every structural or temporal
channel is scientifically closed.

## Decision

Ship two tightly scoped interpretations first:

1. **Authored cosine-palette families for topic identity.** Topic color becomes
   a stable gradient family across wood rims and foliage, replacing the current
   hue-by-array-index rule.
2. **A glow-wire x-ray look.** The existing spine geometry becomes a deliberate
   second reading of the same trees, available as a global look toggle.

Do not put stability, freshness, GC lifecycle, activity, or cross-bucket
relationships into the first pass. Those ideas either lack a calibrated
meaning or require data/identity plumbing the renderer does not have.

## Why these two

Both operate on channels available and honest today:

- Bucket identity is user-authored and stable enough to own a palette.
- Render depth is an aesthetic coordinate and can move through a palette
  without pretending to be a learned semantic measurement.
- The line skeleton is derived from the exact same topology as foliage and can
  expose structure without inventing a second model.

They also fit the existing renderer. Neither requires per-note payloads,
postprocessing, ping-pong framebuffers, a GC event stream, or stable note-to-leaf
identity.

## Product goals

- A tree keeps its color identity if bucket ordering changes.
- The grove remains mostly dark, botanical, and edge-defined—not rainbow fog.
- Foliage remains the default and winning look.
- X-ray mode makes branching easier to inspect and feels intentional enough to
  survive as a second view.
- Every new visual effect has a live workshop control.
- Ten data trees hold 60 fps on the target M3 MacBook at normal display size,
  with no perceptible pause while adjusting controls.
- Decorative channels never masquerade as confidence, recency, importance, or
  semantic distance.

## Non-goals

- One leaf per note.
- Per-note freshness or per-note dissolve.
- Stability-as-blur, mist, jitter, or loss of geometric precision.
- Activity-driven wind.
- Mycelium or cross-bucket connection fields.
- Bloom/postprocessing.
- Changing topology, branch length, girth, planting positions, or E7 behavior.
- Replacing the hub palette or making UI chrome topic-colored.

## Honesty contract

The pass uses three labels in code comments and future controls:

- **Measured:** topology/mass already supplied by the grove data path. This pass
  does not alter their mapping.
- **Raw-data:** a direct field such as `ingested_at`; none ships in v1.
- **Decorative:** authored palette, palette travel, pulse, glow, and x-ray
  treatment. Every v1 addition is explicitly decorative.

The current stability values must not affect geometry or material softness.
They lack a matched `fit_nodes` structural null and measure temporal agreement,
not a calibrated probability that any individual branch is correct.

## Interpretation 1 — topic palette families

### Mapping

`bucket.palette` -> curated IQ cosine-palette coefficients -> color sampled by
render depth and a small animated phase.

The standard palette function is:

```glsl
vec3 cosinePalette(float t, vec3 a, vec3 b, vec3 c, vec3 d) {
  return a + b * cos(6.2831853 * (c * t + d));
}
```

The coefficients are authored aesthetic presets. They are not projected from
embeddings. An embedding projection would be arbitrary, unstable across model
changes, and falsely suggest that color distance carries semantic meaning.

### Palette ownership and fallback

Add an optional palette ID to each bucket declaration:

```yaml
- name: visual-craft
  palette: ultraviolet
  projects: [coolshit, render-decomposition, spacecraft]
  themes: [Visual math & 3D craft]
```

`palette` names a curated registry in
`web/src/lib/grove/palette.ts`; YAML does not carry twelve raw floats. Initial
registry:

- `verdigris` — cool green, oxidized brass, pale mint rim
- `ember` — oxblood, copper, restrained amber
- `ultraviolet` — indigo, violet, cold rose
- `cobalt` — midnight blue, electric blue, silver
- `orchid` — plum, magenta, warm cream
- `citrine` — olive, gold, parchment
- `sea-glass` — teal, blue-green, desaturated aqua
- `oxide` — rust, sienna, blue-grey
- `silver-screen` — charcoal, cool silver, faint lavender
- `chlorophyll` — deep leaf green, yellow-green, bone

Palette assignments are a user taste decision. Until every bucket has one,
fallback selection hashes the bucket name into the curated registry. It must
never depend on array index. BFS/aesthetic mode hashes `seed:<seed>`.

### Material use

Color should reveal identity without recoloring every surface equally:

- **Wood:** retain a dark neutral/bark base. Palette primarily affects the
  fresnel rim and contributes at most 25% to the lit face.
- **Leaves:** palette is the main color, mixed with a neutral botanical base so
  silhouettes remain physical rather than emissive.
- **Buds:** sample the bright portion of the same palette.
- **Roots:** use the same family, reduced saturation and luminance; do not shift
  to a different hue family.
- **Ground/UI:** unchanged.

Sampling coordinate:

```text
t = paletteOffset
  + visualDepth * paletteTravel
  + sin(uTime * 0.35 + phase * tau) * paletteMotion
```

`visualDepth` is the renderer's normalized root-to-tip coordinate. It is a
decorative spatial gradient, not note age. Motion must be slow enough that a
tree retains a recognizable family rather than cycling through unrelated
colors.

### New controls

Extend `GroveParams`:

```ts
paletteTravel: number   // 0..2, default 0.75
paletteMotion: number   // 0..0.25, default 0.04
paletteStrength: number // 0..1, default 0.72
```

All three appear in the knob panel. The defaults should produce a visibly
multitone tree without clipping or overpowering brass UI chrome.

### Files

- `scripts/grove_lab/buckets.py` — optional `Bucket.palette`.
- `scripts/grove_lab/dendro.py` — stamp palette ID in snapshots, without making
  a palette change invalidate topology.
- `ytk/ui/server.py` — serve palette ID per bucket.
- `web/src/lib/grove/datatree.ts` — optional `palette?: string` contract.
- `web/src/lib/grove/palette.ts` — registry, stable fallback hash, coefficient
  types, CPU-side helpers.
- `web/src/lib/grove/shaders.ts` — extracted shared GLSL palette function and
  shader sources.
- `web/src/lib/grove/scene.ts` — palette uniforms/material construction.
- `web/src/lib/grove/tree.ts`, `web/src/routes/grove.tsx` — params/defaults and
  knobs.

### Cost

Small. Four additional `vec3` uniforms per per-tree material and a cosine
evaluation in fragment shaders. No geometry or draw-call increase.

### Kill criterion

Delete or simplify the palette treatment if any of these survives tuning:

- Trees read as generic neon/rainbow shader art rather than botanical forms.
- Bucket identity is less stable than one restrained authored hue.
- Dark wood loses readable volume.
- The palette clips into flat white or black over meaningful screen areas.
- Fragment cost causes a sustained frame rate below 60 fps on the target scene.

## Interpretation 2 — glow-wire x-ray

### Mapping

The existing generated spine lines -> an anatomical x-ray of the same topology.
Palette family supplies color; render depth supplies traveling pulse; no new
data interpretation is introduced.

This ships as a global `foliage | x-ray` look toggle. Foliage remains the
default. Hover-only x-ray is deferred because the scene has no picking system;
adding raycasting would turn a material pass into an interaction project.

### Shader approach

Native WebGL line width is not a portable glow primitive, and there is no
screen-space distance field available to the existing line fragment shader.
Do not pretend that `0.02 / d` can simply be pasted into `lineFragment`.

Use geometry already built for every tree:

1. **Core skeleton:** existing `LineSegments`, palette-sampled, additive, with a
   restrained depth pulse.
2. **Halo/body:** existing tube mesh rendered with an x-ray material—very dark
   face, broad additive fresnel rim, low opacity. This supplies spatial glow
   around the one-pixel spine without bloom or extra geometry.
3. **Roots:** same treatment at lower intensity; roots remain still.
4. **Leaves:** hidden in x-ray mode. No point sprites are introduced.

The x-ray tube material must use the already-built tube geometry and existing
draw calls. Mode switching changes visibility/material selection; it does not
regenerate topology.

### New controls

Extend `GroveParams`:

```ts
wireGlow: number  // 0..2, default 0.8
wirePulse: number // 0..1, default 0.28
wireBody: number  // 0..1, default 0.12
```

The route restores a quiet look chip for `foliage` and `x-ray`. Look choice is
persisted separately from generation params. Knobs remain visible in both
looks.

### Files

- `web/src/lib/grove/shaders.ts` — x-ray tube and core-line fragments.
- `web/src/lib/grove/scene.ts` — explicit object groups or tagged render roles,
  x-ray materials, visibility switching, `setLook` behavior.
- `web/src/routes/grove.tsx` — look chip, persistence, effect knobs.
- `web/src/lib/grove/tree.ts` — new parameters/defaults.

### Cost

Medium. It reuses existing tube and line geometry. Target draw-call count is no
higher than the current scene's already-created wood/line/root objects; foliage
instances are hidden in x-ray mode. No composer, render target, blur pass, or
bloom dependency is allowed in v1.

### Kill criterion

Delete the mode if:

- It reads as a debug wireframe rather than a deliberate anatomical view.
- The halo obscures branch intersections or makes topology harder to follow.
- Ten trees fall below 60 fps or mode switching visibly stalls.
- It only looks acceptable with postprocessing bloom.
- It competes with foliage as the primary identity instead of serving as an
  inspection view.

## Shader architecture

`scene.ts` currently owns all shader strings and material factories. Adding
palette and x-ray variants inline would make experimentation brittle. Extract
only the rendering-source layer:

```text
web/src/lib/grove/
  shaders.ts   GLSL helpers and shader strings
  palette.ts   curated palette registry and stable resolution
  scene.ts     scene lifecycle, geometry, uniforms, materials, visibility
```

Do not introduce a material class hierarchy. A small `TreeMaterials` record is
enough:

```ts
type TreeMaterials = {
  wood: ShaderMaterial
  leaves: ShaderMaterial
  line: ShaderMaterial
  xrayWood: ShaderMaterial
  root: ShaderMaterial
  xrayRoot: ShaderMaterial
}
```

Shared animated uniforms (`uTime`, `uProgress`, `uWind`, DPR) remain references.
Palette uniforms are per tree. Never put mutable palette or dissolve uniforms at
module scope.

Objects should be tagged by role rather than inferred only through
`instanceof`:

```ts
type RenderRole = 'wood' | 'root' | 'leaf' | 'line' | 'bud'
```

This prevents x-ray visibility rules from accidentally exposing the ground or
hiding unrelated meshes.

## Configuration and migration

- Bump local parameter storage to `grove-params-v2`, merging saved v1 values
  over new defaults once before writing v2.
- Persist look under `grove-look-v1`.
- Missing/unknown palette IDs resolve through the stable bucket-name fallback
  and emit no runtime failure.
- Existing snapshots without `palette` remain valid.
- Palette edits do not require topology rebuild. Prefer serving the current
  bucket config's palette at API time; if snapshots also stamp it for provenance,
  the API config value wins.
- E7 readback uses a fixed neutral palette path and must remain visually
  unchanged. The readback route must not inherit topic palettes or x-ray
  controls.

## Performance contract

Target scene: data mode, ten current buckets, foliage defaults, target M3
MacBook, normal browser viewport.

- Sustained 60 fps after growth settles.
- 1% low at least 50 fps over a 20-second orbit.
- No shader compile or mode-switch pause over 100 ms after initial warm-up.
- No increase to canopy/root node caps or leaf instance budgets.
- Device pixel ratio remains capped at 2.
- No new per-frame JavaScript allocation proportional to tree or leaf count.
- No postprocessing pass in v1.

Add a development-only timing readout or repeatable manual benchmark procedure;
do not ship a permanent FPS widget in the hub.

## Verification

### Automated

- Palette resolution is deterministic by bucket name and independent of bucket
  ordering.
- Every curated palette resolves to finite coefficients and sampled colors stay
  within a tolerable display range after final clamp/tone treatment.
- Bucket YAML accepts known palette IDs; unknown IDs fall back safely.
- `/api/grove` exposes palette without centroids or other server-only fields.
- Old snapshots and v1 local params load without error.
- `setLook('x-ray')` and `setLook('foliage')` do not regenerate topology.
- E7 `ReadbackPage` always forces the neutral material path.
- Production build/typecheck succeeds with shader source extraction.

### Visual/manual

- Capture the same seeded camera view in foliage and x-ray modes.
- Inspect all ten palettes together for accidental near-duplicates.
- Inspect epicmap alone for clipping and canopy mud at its high mass.
- Inspect visual-craft and the smallest saplings for palette identity without
  relying on size.
- Drag every new knob through its full range; the browser must remain responsive.
- Orbit through branch intersections in x-ray mode and confirm the core remains
  traceable.
- Verify reduced-motion preference can set palette motion and wire pulse to zero
  without losing the static look.

## Delivery stages

### Stage 0 — freeze a visual baseline

- Record current default params, seed, camera, and data snapshot hash.
- Capture foliage and dormant-wire reference images.
- Add no visual behavior.

### Stage 1 — palette system

- Add registry, config/API contract, uniforms, and knobs.
- Keep the existing HSL path behind a development fallback until palette tuning
  passes the kill criteria.
- User checkpoint: choose/adjust the ten palette assignments in one grove view.

### Stage 2 — x-ray mode

- Extract shader strings.
- Add role-tagged materials and visibility rules.
- Restore the look toggle and add wire controls.
- User checkpoint: decide whether x-ray earns permanent UI or remains a
  workshop-only mode.

### Stage 3 — performance and restraint pass

- Run the target benchmark in both modes.
- Reduce palette strength/glow before reducing geometry quality.
- Verify neutral E7 rendering and existing data/BFS modes.
- Remove the legacy HSL path if the palette system survives.

## Deferred interpretations

### Node freshness glow — next honest data effect

Possible after the API can provide per-node aggregates:

```ts
freshness?: number          // normalized raw aggregate, definition stamped
freshnessCoverage?: number  // fraction of descendant notes with ingested_at
```

It also requires topology-node identity to survive into `TreeNode` and a
per-vertex/per-instance attribute in generated geometry. Until coverage is
meaningful, missing data must render neutral—not old. Freshness may affect a
small emissive rim, never branch size or wind.

### Note lifecycle dissolve — separate project

Requires stable note IDs in the API, deterministic note-to-leaf assignment,
per-instance lifecycle attributes, an ingest/GC event stream, and replay-safe
state. Current leaves are procedural canopy instances, not notes. Do not add a
fake whole-node dissolve and call it note pruning.

### Cache weathering

Requires a production snapshot debt field and a policy whose semantics are
actually shipped. If built, debt may modulate a subtle bark/moss overlay labeled
raw operational state. It must not imply semantic wrongness.

## Rejected seed ideas for this pass

- **Stability as mist/fuzz/jitter:** wrong epistemic mapping; gate is not a
  branch-confidence probability and visual softness harms geometry reading.
- **Wind as ingest cadence:** raw but semantically loud; activity would look like
  importance and moving trees are harder to compare.
- **Mycelium ground:** requires an unvalidated relationship channel and likely a
  feedback/render-target pipeline; high cost, weak product job.
- **Embedding-derived palettes:** unstable and falsely metric.
- **Additive foliage particles:** violates the established form/taste rule.

## Wild backlog

These are decorative research sketches, not v1 commitments:

1. **Anatomical wipe.** A cursor-centered screen-space aperture reveals x-ray
   material beneath foliage, like moving a scanner over the grove. It uses the
   same two valid looks and adds no data claim. Kill if it requires a full
   postprocessing composer or picking becomes fragile.
2. **Cambium bands.** Very faint palette bands travel along wood depth during
   growth replay, leaving the settled tree static. The effect makes the existing
   growth animation feel cellular without pretending the bands are dates. Kill
   if it resembles zebra striping or obscures girth.
3. **Herbarium mode.** Freeze wind, flatten palette motion, raise edge contrast,
   and present the grove as a dark scientific plate for screenshots and close
   comparison. This is a parameter preset, not new geometry. Kill if it is only
   a worse foliage mode.

## Acceptance criteria

The pass is complete when:

- Current buckets have stable, authored palette identities with a deterministic
  fallback.
- Foliage remains the default and looks materially better than the single-HSL
  baseline.
- X-ray mode is legible, palette-consistent, and independently toggleable.
- All six new effect controls work and persist.
- E7/readback remains neutral and unchanged.
- The target performance contract passes in both modes.
- No uncalibrated stability, recency, activity, or lifecycle claim entered the
  renderer.

