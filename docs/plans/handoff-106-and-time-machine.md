# Handoff: #106 semantic domains, then feature D (time machine)

Written 2026-07-25. Self-contained: reads only durable state (the repo, the
open PR, `~/.ytk/`). Epic is #107.

## State at handoff

- **PR #117** is open on branch `feat-a-flow-pulses` and carries three
  rendering features: A (flow pulses), B (ribbon strands), C (bloom), plus
  matplotlib checkpoints for each in `docs/assets/{flow-pulses,ribbons,bloom}/`.
  It is *not* merged. Decide whether to merge it before starting, or branch
  from it — D touches the same file (`web/src/lib/mapRenderer.ts`).
- Closed this session: #105, #112, #101, #10, #11. Merged: #109, #110, #115, #116.
- The map's render loop **parks itself when idle** (#101). Any new
  time-driven animation must add a clause to `animating()` in
  `mapRenderer.ts` or it will freeze the moment everything else settles.
- Two debug query params exist on `/map`: `?motion=on` (overrides the OS
  reduce-motion preference, which is ON on this machine) and `?bloom=off`
  (skips the post chain).

## Task 1 — #106: semantic domains

**The labels in the map legend are still vault directories.** Nothing in the
frontend controls them; the legend renders whatever is in `map.json`.

The chain is `scripts/build_map.py` -> `ytk/mapdomains.py::domain_labels()`
-> `map.json` `all.domains` -> legend.

`ytk/mapdomains.py:75-85` is a hybrid: consumed media gets semantic theme
labels, everything else falls through to `project_from_path()`, which reads
the vault path. That is why the legend mixes "3d/vfx & motion-design craft"
with "epicmap" and "ytk".

`~/.ytk/grove_buckets.yaml` already exists (written 2026-07-12) and is
already read by `ytk/ui/server.py` and `scripts/grove_lab/buckets.py` — it
drives the grove. Nothing in `build_map.py` or `mapdomains.py` reads it.

So the work is: make `mapdomains` use the buckets instead of the path slug,
then re-run `build_map.py`. Per `docs/assets/fog/linkedin-notes.md`, this
**recolours and does not reshape** — positions come from UMAP over the
embeddings and will not move, so fog/strand/junction geometry stays
pixel-identical. Only labels, panel colours, the figure-06 per-domain
ranking, and the majority-vote strand tint change.

Regenerate afterwards: `scripts/plot_assets.py --refresh` (fog) and
`scripts/plot_picking.py`, both of which currently carry provenance labels.

## Task 2 — feature D: time machine

Effort `##`, the lightest item left. From #103: per-note birth-date
attribute + clock uniform + scrubber. The data already exists — no pipeline
work, no re-embed.

It generalises a pattern already in the renderer: the intro sweeps notes in
by phase (`grow = rampf(introT * 1.8 - phase * .8)` in the point vertex
shader). D is the same sweep driven by a date rather than a fixed timer.

Where things live:
- Point buffer packing is in `draw()` under `if (geometryDirty)`, currently
  **28 floats per vertex, stride 112**. A date attribute makes it 29 / 116,
  and the `pointCount = points.length / 28` divisor must change with it.
  Every `vertexAttribPointer` for the point program uses that stride.
- `data.points[i].d` already holds the note date (see the `days` computation
  in the same block, which parses it for the recency filter).
- The web/ribbon program is a separate buffer at **13 floats, stride 52** —
  do not confuse the two.

Acceptance worth keeping: scrubbing to the earliest date should leave the
map nearly empty; scrubbing to today should match the current render exactly.

## Gotchas that each cost time this session

- **Shader linking is a runtime event.** tsc, the linter and 160 unit tests
  all passed a program the GPU refused to link, and the map rendered "Something
  went wrong!" for one commit. Always verify in a browser:
  `uv run --with playwright python scripts/shoot_flow_pulses.py --url <hub>`.
  It runs two arms and asserts motion-on frames differ *and* motion-reduced
  frames are byte-identical. "Frames differ" alone proves nothing — a camera
  still easing satisfies it.
- **GLSL reserved words.** `half` will not compile. Naming a JS helper `use*`
  makes the React hooks linter treat it as a hook.
- **Fresh worktrees need `vp install`** before `vp check` / `vp build` /
  `npm test` resolve.
- **`uv sync --extra lab` alone removes the dev deps.** Use both extras.
- **Fetch before grepping a remote ref.** A stale `origin/master` produced a
  false "the merge dropped the feature" alarm.
- Start every command with `cd <worktree> &&`; bash cwd drifts after `cd web`.
- Use `wt`, never raw `git worktree`. Never push to master.

## Open threads, not blocking

- **The bloom notebook over-predicts by ~1.8x.** `labs/bloom_tuning.py` runs
  the same arithmetic in numpy but the GPU adds 0.43% light where the model
  says 0.76% (`docs/assets/bloom/01-model-vs-gpu.png`). A premultiplied-alpha
  explanation was tried and **refuted** — the measured error was identical
  afterwards. Cause unknown. Marimo is parked by decision; if bloom needs
  retuning, do it against the GPU, not the notebook.
- **One test flaked once** during a rename and did not reproduce. The web
  suite is not perfectly stable.
- C has a validation checkpoint but it currently records a failure to
  validate, which is the honest state rather than a gap to paper over.
