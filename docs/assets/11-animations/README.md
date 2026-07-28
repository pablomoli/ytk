# Animated explainers

Manim scenes for the two overnight experiments. Every number and every point
position is real, loaded from the sidecars in `../09-heatmap-key-moments/` and
`../10-tag-coherence/`.

| scene | explains | length |
|---|---|---|
| `NullModel` | why a size-matched null is the whole experiment (#37) | 37s |
| `ReplayCurve` | do generated key moments land where people rewatch (#144) | 26s |

## Render

```bash
uv run --with manim manim -qm --media_dir /tmp/manim \
    scripts/manim/experiments.py NullModel ReplayCurve
cp /tmp/manim/videos/experiments/720p30/*.mp4 docs/assets/11-animations/
```

Only the finished mp4s are committed. Manim's media dir also holds font caches
and per-animation partial movie files, which are build artifacts.

`-ql` draft, `-qm` 720p30, `-qh` 1080p60. Nothing is installed system-wide — the
`uv run --with manim` env is ephemeral.

## Notes on the build

**ManimCE, not ManimGL.** 3Blue1Brown's own video source is public at
`github.com/3b1b/videos`, but it is CC BY-NC-SA 4.0 and requires `manimgl`
installed from source. This uses the community edition, which is maintained and
has a documented API. The 3b1b repo is a style reference here, not a code source.

**No LaTeX.** `dvisvgm` is not present on this machine (BasicTeX, not full
MacTeX), so `MathTex`/`Tex` cannot render. Every label is `Text`, which needs
only manimpango. Nothing in these scenes requires typeset math.

**The verdict is drawn in z units, not raw cohesion.** `ai-coding` and
`reference` have *different* nulls — a 49-note tag and a 125-note tag have
different spreads — so a shared raw-similarity axis puts one of the arrows in
the wrong place. z is the common ruler, and the scene zooms the ruler out rather
than rescaling the data.
