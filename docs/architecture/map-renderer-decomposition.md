# Map Renderer Decomposition

`mountMapRenderer` is a 1,632-line closure inside
`web/src/lib/mapRenderer.ts`. It owns every mutable WebGL and interaction
resource for one canvas. Extraction must follow ownership boundaries rather
than moving arbitrary line ranges.

## Current ownership

| Concern | Creation and mutation | Disposal |
|---|---|---|
| Point program and buffer | Main vertex/fragment shaders, point upload, focus and time uniforms | Main buffer and program deleted by `destroy()` |
| Terrain | Optional line program plus per-view contour/ridge buffers | Both buffers per view and line program deleted |
| Filament web and junctions | Ribbon program/buffers and junction sprite program/buffers | Every per-view buffer and both programs deleted |
| Fog | Fog sprite program and per-view buffers | Every fog buffer and program deleted |
| Picking | Color-ID framebuffer and texture, block readback, rendered-point index | Texture and framebuffer deleted |
| Bloom | Scene, bright-pass, and ping-pong targets; quad buffer; three programs | Targets, quad buffer, and programs deleted |
| Camera and animation | Scale, pan, orbit, morph, focus, fly-to, easing targets, frame handle | Frame cancelled and momentum cleared |
| Labels | HTML label nodes and SVG leader lines derived from projection and focus | Both containers emptied |
| Input | Resize, mouse, wheel, click, and double-click listeners with wake wrappers | Exact wrapper references removed |

`destroy()` is the single lifetime boundary. No extracted owner may leave
resource deletion to garbage collection or retain a listener after that call.

## Existing witnesses

| Behavior | Existing witness |
|---|---|
| Focus targets, hashes, group identity, label rows, growth phases | `web/src/lib/mapGroups.test.ts` |
| Momentum sampling, release velocity, and decay | `web/src/lib/mapInertia.test.ts` |
| Quantile birth positions and undated sentinel | `web/src/lib/pointBirths.test.ts` |
| Stable unplaced-domain colors | `web/src/lib/mapUnplaced.test.ts` |
| Map API decoding | `web/src/api/map.test.ts` |
| Picking radius and overlap model | `scripts/plot_picking.py` with `docs/assets/02-picking/` measurements |
| Bloom arithmetic and selected constants | `labs/bloom_tuning.py`, `scripts/plot_bloom.py` |
| Fog shell and filament geometry | `scripts/plot_fog.py`, `scripts/plot_ribbons.py` |

These protect pure math and offline visual models. They do not currently prove
WebGL resource lifetime, frame parking/waking, live picking, label cleanup, or
event unregistration.

## Dependency-ordered extraction

1. **Move already-pure helpers.** Extract palette functions to
   `mapPalette.ts` and births to `mapBirths.ts`. Keep the current exports as
   compatibility re-exports until route imports move.
   `mapUnplaced.test.ts` and `pointBirths.test.ts` are the complete witnesses.
2. **Extract projection math.** Create `mapProjection.ts` for world blending,
   camera rotation, clip projection, and cursor-anchored zoom. First add
   `mapProjection.test.ts::projects_flat_volume_and_relief_coordinates`
   with fixed viewport/camera inputs and exact normalized outputs, and
   `cursor_anchored_zoom_preserves_the_anchor_pixel`.
3. **Extract payload-to-buffer builders.** Create `mapGeometry.ts` for point,
   terrain, ribbon, junction, and fog typed arrays without WebGL calls. First
   add `mapGeometry.test.ts::builds_expected_vertex_counts_strides_and_view_keys`
   using one minimal `MapData` fixture and assert every stride, count, and
   optional-view omission.
4. **Extract WebGL resource owners.** Create `mapGlResources.ts` with
   `Program`, `BufferSet`, `Target`, and idempotent `dispose()` functions.
   First add
   `mapGlResources.test.ts::disposes_every_created_buffer_texture_framebuffer_and_program_once`
   in Chromium. Wrap the real WebGL context deletion methods, create every
   resource kind, dispose twice, and assert one deletion per created handle.
5. **Extract picking.** Create `mapPicking.ts` around the color-ID target,
   padded draw, block read, and nearest-hit selection. First add
   `mapPicking.test.ts::returns_the_nearest_visible_point_in_an_overlapping_pick_block`.
   Render two IDs into a 64 by 64 real Chromium WebGL canvas, read the center
   block, and assert distance beats draw order. Keep `scripts/plot_picking.py`
   as the corpus-scale calibration witness.
6. **Extract labels.** Create `mapLabels.ts` with a DOM owner receiving the
   pure projector and current focus. First add
   `mapLabels.test.ts::rebuilds_for_focus_repositions_for_camera_and_clears_on_dispose`.
   Assert label text, leader endpoints, node reuse during camera movement, and
   empty containers after disposal.
7. **Extract input and camera control.** Create `mapController.ts` around
   pointer samples, drag/orbit state, wheel anchors, focus clicks, and the
   `wake` callback. Existing inertia tests protect velocity math. First add
   `mapController.test.ts::registers_each_input_once_wakes_on_mutation_and_removes_exact_handlers`
   and dispatch resize, drag, wheel, click, and double-click events in Chromium.
8. **Extract frame scheduling.** Create `mapFrameLoop.ts` for easing,
   `animating()`, frame parking, and wake-up. First add
   `mapFrameLoop.test.ts::parks_when_settled_and_wakes_without_using_the_idle_gap`
   with a controlled animation-frame clock, plus
   `keeps_running_only_for_visible_motion_allowed_pulses`.
9. **Extract scene passes and bloom.** Create `mapScene.ts` and
   `mapPostprocess.ts` only after resource owners exist. Add
   `mapPostprocess.test.ts::falls_back_to_direct_scene_render_when_a_post_program_fails`
   by forcing one link failure, and
   `composites_a_bright_pixel_without_changing_premultiplied_alpha_contract`.
   Continue running the bloom and fog notebooks for calibrated constants.
10. **Reduce the coordinator.** `mountMapRenderer` should construct owners,
    connect state, expose the unchanged `MapRenderer` API, and dispose owners
    in reverse creation order. Before deleting the closure implementations,
    add
    `mapRendererLifecycle.test.ts::mounts_wakes_picks_focuses_and_destroys_without_leaks`.
    The test mounts a minimal real canvas, drives one public update of every
    kind, calls `destroy()` twice, then asserts no active frame, listeners,
    labels, leaders, or undeleted WebGL resources remain.

No step may change shader constants, buffer layouts, render order, accessibility
motion behavior, or the public `MapRenderer` interface unless a separate ticket
adds a witness for that change.
