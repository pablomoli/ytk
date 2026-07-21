# Growth page: realm-first DNA + run-to-rest performance

Date: 2026-07-21
Status: approved direction, pending spec review
Scope: `web/src/lib/growth/` (dna, topology, scene, philosophy, shaders), `web/src/routes/growth.tsx`, `~/.ytk/growth_philosophy.md` format. No backend changes.

## Problem

1. Organisms fragment into scattered dots ("bacteria") instead of reading as one
   cohesive specimen. Cause: the dominant tag-vote operator selects the Gray-Scott
   regime, and two of the six anchors (BUD "mitosis", STIPPLE "maze") are
   spot-splitting/granular families; the topology seeds up to 42 nodes down to
   radius 0.028 whose droplets become disconnected speckle colonies.
2. No realm identity: two tech themes can land in different chemical families
   because the regime follows whichever operator wins the tag vote. Themes of the
   same realm should share a recognizable pattern language.
3. Initial organisms are small (root radius 0.11-0.16 of the dish).
4. Performance (measured, M3, dpr=1): 25 fps steady-state vs 120 fps paused —
   ~32 ms/frame is simulation; 12.6 s of main-thread blocking during load with
   individual 2.6-2.8 s tasks from synchronous replay bursts that run up to three
   times (initial select, then library-page and cover-palette arrivals each
   re-trigger a full re-seed).

## Design

### 1. Realm layer

- New type `Realm = { id, label, match: RegExp, regime: RegimeName, motif: number }`.
- `RegimeName` indexes a table of *cohesive-only* Gray-Scott anchors (connected-mass
  families). The fragmenting anchors (mitosis, maze) are retired.
- Default realms (fallback when the philosophy file has no `## realms` section):

  | realm        | tag flavor                                   | regime      | reads as          |
  |--------------|----------------------------------------------|-------------|-------------------|
  | tech         | ai-, llm, dev-tools, programming, agents     | veins       | circuitry lace    |
  | visual-craft | creative-coding, shader, design, typography  | flow        | bleeding ink      |
  | body         | fitness, combat, training, nutrition         | coral       | lobed coral       |
  | science      | math, physics, quantum, neuroscience         | labyrinth   | fingerprint whorl |
  | media        | film, cinema, anime, story                   | membrane    | holed membrane    |
  | maker        | hardware, diy, 3d-print, electronics         | lobes       | chunky budded mass|
  | misc         | (no match)                                   | coral       | —                 |

- Classification: sum tag counts per realm's `match`; highest total wins; stamped as
  `SeedDNA.realm`. `dnaToRD` reads the realm regime; operators no longer select the
  family. Operators remain as interior-detail modulation (LACE thins veins via
  diffB, STIPPLE drives display-shader texture) — demoted, not removed.
- Authoring: `growth_philosophy.md` gains an optional section parsed by
  `parsePhilosophy`:

  ```
  ## realms
  tech: ai-|llm|dev-tools|agents => veins
  body: fitness|combat|training => coral
  ```

  Lines are `realm-id: tag-regex => regime-name`. Unknown regime names fall back to
  coral with a console warning. The section fully replaces the defaults when present.

### 2. Cohesion and initial size

- `topology.ts`: root radius `0.11 + density*0.05` → `0.20 + density*0.06`
  (half-dish specimen); node cap 42 → 18; maxDepth 4 → 3; min branch radius
  0.028 → 0.05; child reach `radius*(0.95..1.6)` → `radius*(0.7..1.1)` so lobes
  always overlap the parent mass.
- `scene.ts` `makeSeedTexture`: droplet gaussian denominator `node.radius*0.5` →
  `*0.85`; domain field widened in proportion so the substrate is one connected
  ragged region.
- Event droplets: radius ranges scaled ~1.4x; `maxSpread` 0.3 → 0.34.

### 3. Realm-locked mutations

- `mutateDNA` carries `realm` through unchanged; since the regime is keyed by
  realm, variant tiles can never jump chemical family. Variation surfaces: palette,
  density, motion, granularity, asymmetry, operators (interior detail).
- Migration: adopted DNAs in localStorage lack `realm`. On load, if missing,
  re-classify from the theme's tagCounts (or `misc` for the reliquary preset).

### 4. Performance: run-to-rest with an ambient tick

- **Event-driven stepping.** Full-rate simulation (current per-DNA step counts)
  only while an event droplet is animating or settling. At rest the stage runs one
  simulation pass every 3rd frame (ambient life; flow/worms keep crawling at ~3% of
  current cost). Tiles never idle-step: after catch-up they are baked — drawn from
  their last texture only. Tab hidden (visibilitychange) pauses everything.
- **Amortized replay.** Settled-event replay moves out of the synchronous loop:
  a replay queue advances at most 2 events per animation frame behind the existing
  "assembling cultures" status message. Settle budgets drop: 24 → 8 stage,
  10 → 4 tiles. Applies to both `setOrganism` catch-up and `catchUpTiles`.
- **Seed once.** `growth.tsx` defers the first `setOrganism` until profile,
  library page, and cover palette have all resolved (single fingerprint change),
  eliminating the triple burst. Palette arriving later than 5 s proceeds without it
  rather than re-seeding.
- **Resolution.** `STAGE_SIZE` 1024 → 512; composer pixel ratio capped at 1.5 on
  this page. RD scale constants retuned once so pattern wavelength looks unchanged
  at dish size.
- **Status churn.** `emitStatus` during an active event throttles to ~4 Hz instead
  of every frame.

### 5. Realm motif accent (optional polish, last)

- `uMotif` uniform: one restrained per-realm interior accent (tech: faint
  directional flow bias; body: radial ribbing), within existing glow/saturation
  constraints. Ships only if it survives the visual check; the realm identity must
  already read from regime + silhouette alone.

## Testing and verification

- `dna.test.ts`: realm classification (tag votes, tie → misc), regime pinning,
  mutation realm-lock, localStorage migration fallback.
- `topology.test.ts`: node count ≤ 18, min radius ≥ 0.05, all children overlap
  parent (distance < parent radius + child radius).
- `philosophy.test.ts`: `## realms` parsing, unknown regime fallback, absent
  section → defaults.
- Perf acceptance (headless, M3, dpr=1): steady-state ≥ 55 fps on /growth; no
  single long task > 250 ms during load; visual check screenshots of one theme per
  realm (paused) reviewed before ship.

## Out of scope

- Backend/profile changes; grove page; realm reuse in map/creators (future).
- Persisting converged sim textures to IndexedDB (noted as a possible follow-up if
  replay amortization still feels slow on revisit).
