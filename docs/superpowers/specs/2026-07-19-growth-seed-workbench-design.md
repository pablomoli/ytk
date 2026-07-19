# Growth seed workbench — moodboard-steered redesign of /growth (issue #80)

Date: 2026-07-19
Status: approved (user), supersedes the "Bio-Digital Reliquary" locked direction
in the #80 demo-stage handoff comment.

## Reframe

The prior handoff locked a single aesthetic upfront and gated progress on shader
iteration toward it. This redesign moves taste from specification time to
selection time, following the rndyrbrts taste-to-generation pipeline (vault note
`sources/instagram/rndyrbrts-2026-05-18-DYeHzvgCURl.md`): metadata drives
generation, named seeds with operator vocabularies replace a mandated style, and
art direction happens by browsing mutations and picking survivors.

Kept from the demo: the state-texture engine (384x384 RGBA, ping-pong render
targets, localized update pass) and the invariant that growth is incremental —
old tissue never reshuffles.

Dropped: the hardcoded 13-node seed topology, the 1-bit related/novel event
vocabulary as the primary interface, and the reliquary as mandate (it becomes
one preset seed).

## Concept unit

One organism per profile theme (from `/api/profile`). Themes carry
`evidence_ids`, exemplars with sources, tag provenance, weight, and freshness —
each new note grounded in a theme is that organism's next growth event.

Stability rule: organisms key on theme ids. Adopted DNA and event-replay
position persist independently of profile re-runs (localStorage at this stage),
so re-synthesis never silently regrows or reshuffles a grown organism. Same
invariant as grove.

## SeedDNA

```ts
type SeedDNA = {
  themeId: string;
  name: string;              // mechanical for now; LLM naming is a later layer
  palette: string[];         // 5 hex colors
  operators: OperatorWeights; // DEEPEN BUD LACE STIPPLE BLEED MEMBRANE, 0..1
  params: { density: number; motion: number; granularity: number; asymmetry: number };
};
```

Derivation is a pure function of the theme snapshot:

- **Operators**: static table maps tag families to operator emphasis
  (creative-coding → LACE/BLEED; fitness/combat → DEEPEN/BUD; physics/math →
  STIPPLE/MEMBRANE; ai/ml → LACE/STIPPLE; design → BLEED/MEMBRANE; fallback
  uniform). Weighted by the theme's actual tag counts, normalized.
- **Palette**: k-means (k=5) over pixels of the theme's exemplar cover images
  fetched same-origin via `/api/cover`. Organisms inherit the colors of the
  saved content.
- **Params**: theme weight → density; fresh_note_count ratio → motion;
  n_notes → granularity; a hash of themeId → asymmetry baseline.

Mutations M01–M04: seeded jitter of operators/params within constraint bounds.
Same DNA + same mutation seed = identical result, deterministic.

Approach chosen: deterministic skeleton now, shaped so a bounded LLM layer
(naming, philosophy interpretation) can drop in later without changing the
visual pipeline.

## Topology

The seed organism is generated, not hand-placed: recursive asymmetric branching
seeded by hash(themeId), with branch count, curvature, spread, and lobe
eccentricity taken from DNA params and constraint floors. This removes the
hub-and-spoke read at the topology level rather than patching it in the shader.

## Events

Replaying a theme's evidence notes chronologically grows the organism from
nothing to present. Each event carries the note's tags (per-stroke operator
emphasis) and a hue drawn from the note's own cover palette when available.
Related-vs-novel is derived (tag overlap with the theme's dominant tags), not a
button. The manual `+ related` / `+ novel` buttons move to a debug drawer.

## Workbench UI (route /growth)

Three zones, mirroring canvas-dna-workbench.html:

1. **Organism gallery** — every theme as a small live canvas with name and
   swatches; click to select. (His "Browse DNA Seeds" grid.)
2. **Main stage** — selected organism large, with metadata chips: tags, palette
   swatches, note count, event position. (His catalog cards.)
3. **Mutation row** — M01–M04 of the current DNA, pick-to-adopt. Plus: random
   DNA seed, new mutation set, abstraction slider, pause/reset. The abstraction
   slider blends the render pass from figurative (full organism shading) toward
   a raw operator field (palette bands and stipple only) — display-only, never
   written into state.

All mutation canvases share one WebGL renderer and update material; each
variant is its own pair of state textures with different uniforms.

Persistence at this stage: localStorage (`adopted DNA per theme, replay
position`). Hub-side persistence arrives with live event wiring (out of scope).

## Philosophy axis

`~/.ytk/growth_philosophy.md`: YAML frontmatter of hard constraints the code
enforces now (glow ceiling, hue rules, curvature/asymmetry floors — "never
reads as a graph" becomes a clamp), followed by free-text philosophy for the
future LLM layer. Served and edited via GET/PUT `/api/growth/philosophy`
following the grove-buckets verbatim-roundtrip pattern. This is the only
backend change.

## Reliquary

Encoded as one hand-written preset SeedDNA ("bio-digital reliquary") visible in
the gallery, competing in the picker like any other seed.

## Testing

- Unit tests (vitest, existing pattern): DNA derivation, tag→operator mapping,
  mutation determinism, constraint clamping, palette k-means on synthetic data.
- `npm run build` green.
- Visual verification is the mutation picker itself; headless screenshot pass
  against real profile data before handoff.

## Addendum (2026-07-19, after user review): reaction-diffusion + dither

User feedback on v1: pixelation/haziness killed the organic feel; the authored
branch topology read as the grove's pattern again. Direction revised:

- Field dynamics are now Gray-Scott reaction-diffusion (simulated
  morphogenesis, not authored shape). Dominant operator selects a cohesive
  regime anchor (coral, mitosis, worms, maze, flow, holes); `dnaToRD` maps DNA
  to feed/kill/diffusion/steps.
- The state's alpha channel is a growth domain: the reaction starves outside
  it, and each note's droplet expands it locally — the silhouette itself is
  the record of growth. Droplets clamp within reach of the organism centroid.
- Render is palette quantization through a procedural 8x8 Bayer threshold at
  screen resolution (crisp by construction); simulation upscaling never
  reaches the screen. The abstraction slider now blends dither → smooth.
- Simulation runs continuously (steps-per-frame from DNA motion); resolution
  raised to 768 stage / 256 tiles.
- Topology remains only as asymmetric placement of initial droplets.

## Out of scope (later phases)

- Live ingest events perturbing organisms (needs hub persistence).
- LLM seed naming and free-text philosophy interpretation.
- Ingest-side palette extraction in Python (client-side sampling suffices now).
- Grove/map cross-links.
