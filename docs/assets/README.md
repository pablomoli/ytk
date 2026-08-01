# Visualization house style

Every figure and animation in this repo — committed asset or throwaway
checkpoint — renders under one design, and that design lives in code, not in
this file. This README says where the code is and what the contract around it
is. If a rule here and the code disagree, the code wins; fix the README.

## The one rule

**Import the style; never restate it.** `scripts/plot_assets.py` is the single
source: palette, typography, figure anatomy, panel framing. Scripts that
hardcode their own hex values or fonts drift, and drift between figures in the
same series reads as sloppiness in post material. The import pattern
(`scripts/plot_picking.py` is the reference consumer):

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ on path
from plot_assets import BG, GOLD, MUTED, figure, frame_panels, panel_title, style_axes
```

Importing the module also sets the house font globally (CMU Serif, mathtext
`cm`) — `plt.style.use("dark_background")` afterwards touches colors only,
so the order import-then-style is safe and conventional.

## Matplotlib

What `plot_assets` provides, and what every figure uses:

- **Ground and ink**: `BG #08080a` figure ground, `PANEL #000000` interiors,
  `FRAME #2e2e36` borders, `TEXT #eceae7` / `MUTED #9a968f` ink.
- **Accents**: `GOLD #f2b950`, `BLUE #5a8cff`, `RED #ff4d6d`,
  `PURPLE #9159ff`, `CYAN #7fd4ff`, `DIM #3a3a42`. Continuous data takes
  `saturated_magma()` with `punch()` gamma-lift, not raw magma.
- **Anatomy**: `figure(w, h, number, kicker, title, meta)` builds the header
  block — `FIGURE NN` kicker in gold, large serif title, hairline rule, muted
  meta line carrying the real numbers. Panels get `panel_title()`,
  2D axes get `style_axes()`, 3D axes get `fit3d()`. Before saving, always
  `frame_panels(fig)` then `fig.savefig(out, dpi=DPI, facecolor=BG)`.
- **Backend**: `matplotlib.use("Agg")` before pyplot; figures are files, never
  windows.
- Matplotlib is not a project dependency — run with
  `uv run --with matplotlib python scripts/<script>.py`.

The meta line is part of the design: it carries the measured quantities
(counts, bandwidths, scores) so the figure is self-reporting. A figure whose
title claims something its meta line does not quantify is incomplete.

## Manim

Animated explainers use **ManimCE** (never ManimGL — see
`docs/assets/11-animations/README.md` for the licensing story) via ephemeral
envs: `uv run --with manim manim -ql ...`, media dir outside the repo
(`/tmp/manim` or the session scratchpad), only finished mp4s committed into
`docs/assets/`.

- **Colors come from the same module**: `from scripts.plot_assets import BG,
  GOLD, ...` — the reference consumer is `scripts/manim/semantic_domains.py`.
  A manim clip and its companion matplotlib stills must be indistinguishable
  in palette.
- **No LaTeX.** `dvisvgm` is absent on this machine (BasicTeX); `MathTex`/
  `Tex` will fail. Every label is `Text` (manimpango).
- **The cairo static-partition trap** (measured, twice): the cairo renderer
  bakes every mobject added before the first animated-or-updated mobject into
  a frozen per-play background. Anything that must move or change in a play
  must itself be animated in that play, and any updater's invisible anchor
  must be the scene's FIRST add. The war stories are in
  `scripts/manim/flow_pulses.py` and `semantic_domains.py` docstrings.
- **Verify motion by pixel-diff, never by exit code**: extract two frames
  inside the animation window (ffmpeg), `ImageChops.difference(...).getbbox()`
  must be non-None. A render that exits 0 can still be a frozen frame.

## Checkpoints vs. assets

Two audiences, one style:

- **Assets** (`docs/assets/NN-*/`) are post material — committed, numbered
  series, real data only, reproducible from a script in `scripts/`.
- **Checkpoints** are working artifacts rendered mid-task to catch mistakes
  before they ship (a layout that scores well but reads as noise, a spring
  constant that oscillates). They live in the session scratchpad, are never
  committed, and are sent to the user for review. They wear the same house
  style — a checkpoint the user has to squint at defeats its purpose.

## Provenance

Figures rendered from repo state stamp the short commit SHA in their footer or
meta line. History rewrites can strand old stamps —
`docs/assets/memory-field/PROVENANCE.md` records the one that happened; the
lesson is stamp-at-render, and when comparing figures across engine or data
changes, re-render everything under one version rather than mixing stamps
(`git log` is the arbiter when a stamp no longer resolves).
