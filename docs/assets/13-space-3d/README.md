# The 3D figures, with the camera moving

Additive to the stills in `../09` through `../12` — none of those were replaced.

| scene | shows | length |
|---|---|---|
| `TheCone.mp4` | the corpus, an isotropic control, and the centred corpus, with the origin marked | 33s |
| `TagInSpace.mp4` | `ai-coding` as a region, then `reference` as confetti, camera held through the swap | 25s |
| `CorpusSolid.mp4` | 493 notes coloured by source, orbiting | 19s |

## Why these exist alongside the stills

A still 3D scatter is ambiguous by construction. Depth reads as size, and an
apparent cluster can be an artifact of the viewing angle. Figure 11 in
`10-tag-coherence` claims *"there is no angle from which `reference` looks like a
cluster"* — which a single fixed angle cannot demonstrate. An orbit can.

`TagInSpace` holds the camera still across the highlight swap deliberately: the
layout is visibly identical and only membership changes, so the difference
cannot be attributed to a different projection.

## Subsampling, stated plainly

Background clouds are **200 of 493 notes**, seeded so the same notes drop on
every render. **Highlighted tag sets are never subsampled** — those are the
subject being measured, and thinning them would misrepresent the result.

The reason is cost, not aesthetics: every dot is a real sphere that manim
depth-sorts on every frame, and camera rotation means every frame is a fresh
sort. A first attempt at all 493 notes with full-resolution spheres did not
finish a draft render in ten minutes.

## Render

```bash
uv run --with manim manim -qm --media_dir /tmp/manim \
    scripts/manim/space3d.py TheCone TagInSpace CorpusSolid
cp /tmp/manim/videos/space3d/720p30/*.mp4 docs/assets/13-space-3d/
```

Roughly 20 minutes for all three at `-qm`. Only the finished mp4s are committed;
manim's media dir also holds font caches and per-animation partial movie files.

Coordinates come from `scripts/manim/space3d.json`, exported from the frozen
`vectors.npz` in `../10-tag-coherence/`, so the videos and the stills are drawn
from the same numbers.
