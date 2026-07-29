# Shader track handoff: brainstorm brief for the grove's decoration pass

For a NEW session (and an external model invited to brainstorm freely).
The grove earned this: E7 readback passed (owner recognized his own trees,
3/3 primaries, 6/6 identification), and review v6 explicitly green-lit
decoration as product work — "build the shaders because the personal
readback result was encouraging, not because the representation is
scientifically closed." The science continues in parallel (replay v3 was
running when this was written; `morning-decisions.md` holds the cache
policy). Decoration must not wait on it.

Your job: propose INTERPRETATIONS — mappings from the data channels below
to visual channels — plus wild ideas we did not think of. Constraints and
taste rules are hard; everything else is open.

## What exists (files)

- Renderer: `web/src/lib/grove/{tree,scene,leaf,datatree}.ts`,
  route `web/src/routes/grove.tsx`. Pipeline: node tree (data-native from
  `/api/grove` or BFS aesthetic mode) -> centripetal Catmull-Rom chains ->
  parallel-transport ring stitching -> instanced crafted leaf cards
  (bezier outline, cupped, ~8 tris). One wind field shared by wood and
  leaves; roots pinned to zero wind; hemisphere rule; per-tree tint is
  currently a single HSL hue by tree index (`scene.ts` ~line 176) — the
  most obvious thing to replace.
- Shaders live inline in `scene.ts`: tube vertex/fragment (fresnel rim,
  clamped-cosine growth ramp `ramp()`, `windSway()`), leaf instancing
  shaders, additive line shader (the dormant "wires" look), bud points,
  translucent ground disc. Growth phase = `uProgress` vs per-vertex
  `depth` 0-1.
- Data: `/api/grove` serves per-bucket topology {nodes: {id, parent,
  mass, persistence, exemplars}, n_notes, stability}. Snapshots at
  `~/.ytk/grove/*.tree.json`.
- Source notes that seeded this track (in the vault,
  `second-brain/sources/youtube/`): an-introduction-to-shader-art-coding
  (IQ cosine palettes `a+b*cos(2pi(c*t+d))`, inverse `0.02/d` neon glow),
  dissolve-effect-react-three-fiber-tutorial (noise + step() alpha,
  HDR border color x~50 for bloom edges; TRAP: module-scope uniforms are
  shared across instances — dissolving elements need per-instance
  attributes), what-do-slopes-even-do-in-touchdesigner (derivative-
  displaced feedback, blur-the-source-first), video-to-particles
  (channels-as-axes reinterpretation, reference only).

## Taste rules (hard constraints, learned the hard way)

1. NO additive point sprites for foliage — rejected as "ai slop." The bar
   is real, lit, edge-defined geometry. Additive glow is fine for the
   WIRES look and rims, not as a substitute for form.
2. Foliage is the look; the wires look exists behind the scenes and is
   only viable WITH the glow treatment — that is this track's chance to
   revive it as a second read of the same trees.
3. Hub theme: brass #e2b04a, Newsreader, lowercase, dark ground
   (#0a0a0c). Trees may be colorful; UI chrome must stay quiet.
4. Complexity budgets are law: shared node caps, leaf-instance striding,
   knob debounce (~160ms). Nothing may hang the workshop. M3 MacBook,
   integrated GPU, one canvas at 60fps with 10 trees.
5. The knob panel stays. Every new effect gets a knob.
6. Honesty tiering is part of the design language (see below): the
   renderer must not imply precision the data does not have.

## Data channels, with honesty labels

| channel | status | notes |
|---|---|---|
| bucket identity + n_notes | SOLID | user-authored buckets; n spans 2-2065 |
| node mass (girth) | SOLID + LEGIBLE | E7: mass placement was readable (epicmap payload clear-read) |
| topology (parent/child) | SOLID for ai-building-like buckets; DECORATIVE branch identity for epicmap (no reproducible flat partition — its coarse geometry reproduces, named branches do not) |
| persistence (branch length) | RENDERED BUT UNAUDITED | staleness under the cache was never measured until replay v3; treat as approximate |
| stability gate per bucket | RAW numbers exist (`gate72.json`: fit_nodes_triplet 0.622/0.742/0.947) | held from production stamping pending a null; fine as a decoration input |
| ingested_at timestamps | NEW, sparse | shipped 2026-07-13; only notes ingested from now on carry it — coverage grows daily |
| exemplar titles per node | SOLID | up to 3 per node, already served |
| gc/prune lifecycle | EVENT STREAM | `ytk gc` removes notes; no visual today |
| burstiness / drift / recency-mass | KILLED or UNRESOLVED | failed stability gates; do not encode as if meaningful |

## Seed interpretations (react to these, rank them, beat them)

1. **Cosine palettes as topic identity.** Replace the single HSL tint
   with an IQ palette (4 vec3 knobs) per bucket; depth/growth/pulse
   sample along t. Identity becomes a gradient family, not a hue. Small
   change (scene.ts materials), big identity win. Open question: derive
   the 4 vectors from the bucket (hash? centroid projection?) or author
   them in the buckets YAML like everything else the user owns?
2. **Uncertainty as atmosphere.** The per-bucket stability gate modulates
   structural crispness: visual-craft (0.947) renders sharp, epicmap
   (0.622) gets a softer, mistier canopy — fresnel width, leaf edge
   fuzz, slight vertex jitter. Honest rendering: named-branch confidence
   IS lower on epicmap; show it instead of hiding it.
3. **Freshness as glow.** Now that ingested_at exists: leaves from
   recently ingested notes carry an emissive rim that decays over days or
   weeks (raw-data tier, no model claims). The tree literally glows where
   it is growing. Needs per-instance attributes, not shared uniforms.
4. **Dissolve as lifecycle.** `ytk gc` prunes a note -> its leaf
   dissolves (noise + step alpha, HDR border for the burning edge);
   ingest -> materialize in reverse. The trap from the source note
   applies: per-instance progress attributes.
5. **Glow wires as the second read.** The dormant wires look + inverse
   `0.02/d` falloff = an x-ray mode of the same grove: skeleton +
   pulse, palette-tinted. Could be the hover/inspect state rather than a
   global toggle.
6. **Mycelium ground.** Slope-feedback flow field on the ground disc
   (blur-the-source-first), slow, dark, connecting tree positions —
   possibly weighted by cross-bucket nearest-neighbor relationships
   (raw tier; the mind-systems "magnet" is unconfirmed, keep it abstract).
7. **Staleness as weathering.** When the cache policy ships, a tree's
   attached-since-rebuild debt could show as bark desaturation or moss —
   the tree visibly "needs tending." Blocked on the policy landing;
   design now, wire later.
8. **Wind as cadence.** Per-tree wind amplitude from recent ingest
   activity (raw tier). A busy week literally stirs the tree.

## What to return

Ranked interpretations, each with: name; data channel -> visual channel;
honesty tier (measured / raw-data / decorative — decorative is allowed,
it just cannot masquerade); one-paragraph shader approach with the
specific file it touches; cost (S/M/L); a kill criterion (what would make
us delete it). Then a WILD section: at least three ideas that ignore the
seed list entirely (respect only the taste rules). Prefer few strong
proposals over coverage; flag any seed idea above that you think is
wrong-headed and say why.
