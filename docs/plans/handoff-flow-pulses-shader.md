# Handoff: flow pulses along the filament strands (feature A)

Self-contained brief for implementing the first shader rung after the #101
typing/linting gate. Written 2026-07-24 from the shader-roadmap session.
Context: docs/math/terrain-derivation.md, docs/assets/fog/05 (traced
strands), issues #100 (volume roadmap) and #101 (perf + strict-typing
gate). Related sessions: briefs 034-039 in the vault.

## What to build

Pulses of light traveling along each strand of the /map filament web —
brightness modulated by `sin(arclen * FREQ - time * SPEED)` in the
fragment shader. The strand's arc-length coordinate is the one new piece
of data; everything else exists.

## Where things live today

- Renderer: `web/src/lib/mapRenderer.ts`, all in `mountMapRenderer`.
  - Web shaders: the `webVertex` / `webFragment` template strings near the
    top (search `webVertex`).
  - Buffer build: the `build()` closure under the
    `--- filament web resources` comment. Current layout: **7 floats per
    vertex** `[x, y, z, r, g, b, density]`, GL_LINES pairs, stride 28.
  - Draw pass: search `filament web: lives in the embedding-3D` — sets
    webU uniforms, `vertexAttribPointer` offsets 0/12/24, stride 28.
  - A `time` value already reaches `draw(now * .001)` and is fed to the
    POINT program's `time` uniform — the web program has no time uniform
    yet; add one.
- Payload: `~/.ytk/map.json` -> `all.web.filaments` / `content.web.filaments`,
  vertices `[x, y, z, label, density]` (see `MapWeb` in
  `web/src/api/map.ts`). Strands are ordered and near-uniformly spaced by
  construction (predictor-corrector tracer, `ytk/ridges.py::trace_filaments`)
  — which is exactly why arc length is trustworthy. No payload change
  needed: compute arc length in JS at buffer build.

## Implementation sketch (~30-40 lines)

1. In `build()`: per filament, running sum of segment lengths -> per-vertex
   `alen` (absolute, in layout units; do NOT normalize per strand or pulses
   will travel at different speeds on different strands). Emit as an 8th
   float -> stride becomes 32; offsets pos@0 col@12 den@24 alen@28.
2. `webVertex`: `attribute float alen; varying float al;` pass through.
3. `webFragment`: add `uniform float time;`
   `float pulse = .78 + .22 * sin(al * 38.0 - time * 2.2);`
   multiply into the existing alpha. Tune FREQ (38 ~ wavelength .17 layout
   units) and SPEED (2.2 rad/s) by eye on the epicmap spine.
4. `webU` gains `time`; set it in the web draw pass from the same clock the
   point program uses.
5. **Respect `reduceMotion`** (already read via matchMedia in the mount):
   freeze the pulse phase (pass a constant) when set.

## Gotchas (learned the hard way; see memory + session briefs)

- Stride change touches every `vertexAttribPointer` call of the web
  program AND `count: segments.length / 7` -> `/ 8`.
- The Bash cwd drifts after `cd web && vp build` — start every git/uv
  command with `cd /Users/melocoton/Developer/ytk &&`.
- Deploy chain for frontend changes: `vp build` -> commit dist -> deploy
  from clean export (`git archive HEAD | tar -x -C tmpdir`, then
  `uv tool install --reinstall <tmpdir>`) -> INSPECT
  `/api/ingest/status` output first, THEN `launchctl kickstart -k
  gui/501/com.ytk.hub` as a separate command. Never chain check+restart.
- Parallel Claude sessions may share the tree: `git add` explicit paths
  only, never `-A`.
- If the #101 strict TS config has landed, type the new attribute/uniform
  records accordingly.

## Acceptance

- Pulses travel along strands in the 3D `web` view; direction follows
  each strand's vertex order; taper (density alpha) still visible.
- `prefers-reduced-motion`: static strands, no pulse.
- Headless verification (puppeteer, headless from first navigate) +
  screenshot archived as `docs/assets/fog/07-flow-pulses.png` per the
  matplotlib-checkpoint convention (screenshot counts for shader-only
  rungs). SendUserFile it.
- `vp check` + `vp test` green; no payload/pipeline changes, so no
  `--attach-terrain` run needed.
