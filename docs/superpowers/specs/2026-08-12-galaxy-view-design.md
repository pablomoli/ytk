# /galaxy — the galaxy view: travel between the theme planets

Design spec, brainstormed 2026-08-12 (session 060). Builds the road E29-E33
paved: `galaxy.json` (E32: positions, radii, classes), `channels.json` (E33:
moons with thumbnail exemplars, ring partners, spin), `continents.json` +
the organic coast rule (E30), the per-planet survey lessons (E31). The MVP
is a new hub route where the 18 theme planets hang as textured worlds, the
camera flies planet to planet, and every rendered channel is one that
passed its null.

Decisions locked with the owner: new `/galaxy` route (not an orb mode);
galaxy data attached at map build (never served stale from the committed
record); surfaces = baked coast field + GLSL paint (both, composed);
all three earned channels render in v1; the record's matplotlib palette is
the page's palette; diffusion skins are staged behind as #179, and the
surface contract keeps them a drop-in.

## 1. Geometry and camera: shell + travel

Planets sit where E32 measured them: unit directions (the shell), angular
radius `GALAXY_K * n^(1/3)` degrees with `GALAXY_K = 3.00` (sync contract
with `docs/assets/32-galaxy/`; the renderer consumes `radius_deg`
verbatim). World form: sphere meshes centered at `dir * 1.0` with world
radius `sin(radius_deg)` so angular sizes stay honest.

Two camera states, one grammar (orb's focus-flight, one level up):

- **Overview** — camera outside the shell, orbiting it (orb globe-mode
  controls semantics; wheel = orbit radius). The constellation reads whole.
- **Visit** — click a planet: the camera flies to a standoff point outside
  that planet (E31-orbit-clip framing — the world fills the frame,
  coastlines turning, moons orbiting, ring tilted). Click another planet
  (or its ring partner in the caption) and the camera travels along the
  shell to it — the travel arc is animated, never a teleport. Blur/escape
  returns to overview.

No volumetric layout: c3 radii are unvalidated signal and the E32
occlusion verdict is angular. If depth is ever wanted, it is a new
experiment, not a render option.

## 2. Data pipeline: attach at build

**New production module `ytk/galaxy.py`** — the E32/E33 machinery
graduates from `scripts/` (precedent: E29's `spread()` into
`ytk/spheremap.py`). Pure functions over (vectors, themes, dates, c3,
labels):

- `galaxy_block()`: arm-A positions (centroid directions from the content
  cloud's center — closed form, no UMAP), radii, Sudarsky class + hue +
  cohesion/saturation, activity, date coverage.
- `rings()`, `spin()`: E33's corrected gates, recomputed every build
  (seconds). Ring payload: partner theme + z; spin payload: median age,
  band, side.
- `moons()`: E33's triplet-stability gate + core/minority cut, cached in
  `~/.ytk/galaxy-cache.json` keyed by (epoch, member-set hash per theme) —
  the expensive null reruns only for themes whose membership changed. Moon
  payload: size + exemplar (vault path, title, thumb) — path included so a
  moon click opens the NoteViewer.
- `bake_textures()`: per planet, slice-arm positions exactly as E31 built
  them — `spread(radial(member c3))`, no UMAP refit — → E30 organic signed
  distance field at that planet's own calibration (lattice pole at its n) → normalized 8-bit
  grayscale equirect PNG (512x256) in `~/.ytk/galaxy_tex/{theme}.png`,
  plus the superplanet field (the live radial layout, full organic rule)
  at 1024x512 as `superplanet.png`. Cached by the same member-set hash.
  The minimal fBm/softmin/warp needed moves into `ytk/` with the module;
  `scripts/e30*` stay the committed record.

`build_map.py` attaches `content.galaxy` (planets + channels + texture
manifest + epoch + generated stamp) on every rebuild. Escape hatch:
`--no-galaxy` skips the block (and the hub's endpoint 404s with a rebuild
hint, mirroring `/api/orb`'s missing-sphere message).

**Server** (`ytk/ui/server.py`): `GET /api/galaxy` returns the block;
static mount serves `~/.ytk/galaxy_tex/` (same pattern as `/vault-media`).

**Texture contract (the #179 seam)**: the scene consumes one equirect
base texture per planet from the mount, keyed by theme id. A diffusion
skin is a drop-in replacement file cached by the same member-set hash;
the coast bake is the fallback whenever a skin is missing or stale.

## 3. Palette: the record's skin

`web/src/lib/palette.ts` mirrors `scripts/plot_assets.py`: BG `#08080a`,
PANEL `#000000`, FRAME, TEXT, MUTED, GOLD, DIM, the five Sudarsky class
hues, the cohesion→saturation rule (`0.3 + 0.7 * norm(cohesion)`), and
punch gamma (0.72). Sync-contract comments on both sides (TILE_HALF
precedent). The page's ground is BG — the instrument wears the record's
palette, not the observatory tokens. Styling beyond the canvas uses
Tailwind utilities per the CSS policy; no new rules in styles.css.

## 4. Scene: `web/src/lib/galaxy/scene.ts`

- Reuses `lib/orb/controls.ts` and `normalizeWheelDelta`; same
  mount/dispose shape as `mountOrb` (handle with `dispose()`, gsap tweens
  killed on dispose, ResizeObserver).
- 18 `SphereGeometry` meshes, one `RawShaderMaterial` (per-mesh uniforms).
  Fragment shader: sample the baked distance field (equirect uv from the
  planet-local normal), add 2-3 octaves of GLSL fBm to the sampled
  distance (seeded per theme id — micro-detail at close range; geography
  itself never drifts from the bake), then paint the result through the
  saturated-magma ramp baked from Python (`ytk/coast.py::bake_ramp` writes
  `ramp.png` beside the field textures; the LUT is `plot_assets.py`'s
  `saturated_magma()`, embedded; the sync contract is split — five golden
  stops are pinned in every gate, full 256-stop equality needs matplotlib
  and is run by hand via the `lab` extra, since CI never pulls it).
  E30's `fig_field` runs one continuous nearness value across land and sea
  alike, which makes the shoreline a smooth crossing rather than a
  boundary; owner-directed, the renderer instead splits that ramp into two
  non-overlapping bands of the same palette — sea rides `0.05..0.38`, land
  `0.52..1.0`, mixed with a softened `smoothstep(0.490, 0.510, d)` at the
  shoreline. The gap between the bands is the coast: inside and outside
  are unmistakable at overview distance, and each band is wide enough to
  read as its own gradient rather than a flat zone — sea deepens from
  magenta-red near shore to purple offshore, land climbs from orange at
  the coast to cream inland. The sea floor sits above 0 because a sphere
  against the starfield loses its silhouette to a black ocean. Shoreline
  contour in CYAN on the seam. Class hue is **not** used for terrain: 16 of 18 planets are
  class V, so hue-painted worlds made the sky monochrome. Class stays
  encoded in the caption, where it is legible as a letter.
- **Spin**: texture longitude offset advances at a rate mapped from
  median age (fast worlds visibly turn; dormant worlds near-still; planets
  that failed the spin gate get the population median as a neutral slow
  default — the channel encodes only where it earned).
- **Rings**: for the 8 earned planets, a thin annulus in the tangent
  plane, tilted so its plane leans toward the partner planet's direction;
  TEXT color, low alpha (the figures' ring language).
- **Moons**: for the 2 earned planets, thumbnail billboards (atlas-free —
  two `<img>`-loaded textures from `/vault-media/<thumb>`) orbiting at
  1.6r, size ∝ moon member count, slow orbital period.
- **Starfield**: DIM fibonacci points well outside the shell, static —
  depth cue, one draw call.
- Reduced-motion: travel arcs and spin honor `reducedMotion()` (jump-cut
  camera, frozen spin), same as orb.

## 5. Route and interaction: `web/src/routes/galaxy.tsx`

- Nav gains a `/galaxy` link (links-only rule: it is a link).
- Hover planet → caption bar (orb's pattern): label, class, n, activity,
  and — when visiting — the ring partner names as clickable travel
  targets.
- Click planet: overview → visit (fly to it). Visiting another planet
  travels along the shell.
- **Dive**: a "land" affordance while visiting → navigate to
  `/orb?theme=<id>`. orb.tsx reads the new optional search param and
  preselects its existing theme filter (the one orb-side change).
- Click moon → NoteViewer on the exemplar (path ships in the payload).
- Missing galaxy block → ErrorState with the rebuild hint; loading state
  mirrors orb's.

## 6. Testing

- **pytest** (`tests/`): `ytk/galaxy.py` gates reproduce E33's cached
  verdicts on a frozen fixture (planet count, earned sets, exemplar
  paths); texture bake shape/range/wrap (left-right seam continuity of
  the field); member-set-hash cache hit/miss; `/api/galaxy` contract +
  404 path. Consumer tests of `build_map` attach (per the SDD
  covering-tests rule).
- **vitest, real Chromium** (`vp exec vitest run`): palette mirror values,
  spin-rate mapping, equirect uv math, scene mount/dispose without leaks,
  search-param handling in orb route.
- **Live verify** (house rule: renderer changes need pixel proof): run the
  hub, screenshot the canvas twice ~1s apart while a fast planet is in
  frame — non-empty pixel diff proves spin; a second pair during a travel
  arc proves flight. Never trust exit codes for motion.

## 7. Out of scope (staged, each behind its own go)

- **#179** — diffusion planet skins (the texture contract above is its
  seam).
- Coast-D octave-gain sweep toward Richardson ~1.25 (would refine the
  bake's look; the K and rule ship as-is first).
- Per-planet tile layouts inside the visit view (landing goes to the
  theme-filtered orb; E31 refit surfaces stay an experiment result).
- Volumetric depth (requires its own experiment).

## 8. Build notes

- Implementation on a `wt` branch: the docs-gallery session is actively
  registering routes in `server.py` on master; isolation avoids treading
  on it. Merge on explicit go, then `uv tool install --reinstall .` +
  `launchctl kickstart -k gui/501/com.ytk.hub` (post-merge hook handles
  it).
- Cold rebuild cost: moon gate ~2-4 min once, then cached; bakes and
  ring/spin gates are seconds. Acceptable for the ingest-triggered
  rebuild cadence.
