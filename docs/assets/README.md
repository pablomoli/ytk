# Visualization house style

Every figure and animation in this repo — committed asset or throwaway
checkpoint — renders under one design, and that design lives in code, not in
this file. This README says where the code is and what the contract around it
is. If a rule here and the code disagree, the code wins; fix the README.

Scope: figures and animations — matplotlib stills and manim clips. The hub's
own visual identity is a separate layer (`web/src/theme.css`, and the CSS
policy in `CLAUDE.md`). For what the figures in this folder actually found, the
index is `docs/experiments.md`.

## Design intent

Three commitments, in priority order. They decide the arguments the palette
cannot.

**1. Maximize visibility and expression.** A figure is the argument, not a
receipt for one. Spend the pixels. Fill the panel with the data rather than
leaving it framed in air (`fit3d`, cube limits from the data, `set_box_aspect`
zoom). Lift dim ranges into the visible part of the ramp — the fog's median
density is 0.17, which raw magma renders nearly black, so `saturated_magma()`
pushes chroma 35% and `punch()` gamma-lifts before anything is drawn. Render at
`DPI = 200`, which puts finished figures at 2300-3300px wide and survives a
crop. Restraint that costs legibility is not taste, it is a smaller figure.

**2. Geometry over labels.** The claim must be visible in the shape before any
text is read. A label names what the geometry already shows; it never carries
the finding alone. In practice:

- Draw the null as a distribution the observation sits inside, not as a number
  in the caption. "Key moments average 0.30 replay intensity" means nothing;
  0.30 drawn against a null drawn from the same curve means everything, and the
  distance to the human ceiling is a third mark on the same axis (section 09).
- Put the before and the after on one shared axis, in one panel, at one scale.
  Two figures is two arguments (sections 01/05, 06, 07).
- Reorder to reveal. The tag similarity matrix "ranked by z looked uniform;
  clustered, the blocks are obvious" (section 10, figure 04) — seriation is a
  geometric operation that made the finding visible without adding a word.
- Encode with position, length, angle, area, enclosure and connection. z-scores
  go on a common ruler and the ruler zooms out, rather than the data being
  rescaled to fit a shared axis it does not belong on (section 11).
- When a still is ambiguous by construction, move the camera. A 3D scatter
  reads depth as size and can manufacture a cluster from a viewing angle; an
  orbit is the only honest way to claim "there is no angle from which this
  looks like a cluster" (section 13).
- Draw the panel that kills your own claim. Section 09's figure 03 draws both
  regression fits dashed and states the noise floor on the panel, so the
  picture cannot imply a finding the arithmetic does not support.

The target: a figure whose finding survives deleting every annotation.

**3. Self-reporting.** A figure circulates without its section README. The meta
line carries the measured quantities and `verdict()` carries the conclusion, so
it still states what it measured and what it found when it arrives alone.

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

## Colour

Every token is a constant in `plot_assets`. Two of them — `DIM` and `RED` —
are conventions rather than mere colours, and they are what lets a reader carry
one figure's vocabulary into the next.

| token | hex | role |
|---|---|---|
| `BG` | `#08080a` | figure ground |
| `PANEL` | `#000000` | panel interior — darker than the ground, so panels read as wells |
| `FRAME` | `#2e2e36` | panel and figure borders |
| `TEXT` | `#eceae7` | titles, panel titles, primary labels |
| `MUTED` | `#9a968f` | axis furniture, ticks, the meta line, secondary annotation |
| `GOLD` | `#f2b950` | the house accent and the default first series — the strands in 01, the production Qwen space in 23 |
| `BLUE` | `#5a8cff` | second series |
| `CYAN` | `#7fd4ff` | third series, and persistence/continuity where a figure has a fading-in and fading-out set |
| `PURPLE` | `#9159ff` | fourth series, used sparingly |
| `RED` | `#ff4d6d` | the `verdict()` line; also chance lines and thresholds a result is judged against |
| `DIM` | `#3a3a42` | **the null** — shuffles, permutations, baselines, chance bands, majority floors |

**`DIM` is reserved for the null.** Every shuffled-label histogram, every
majority baseline, every chance band is DIM, in every section. That is the
single most load-bearing colour rule here: a reader learns once that grey is
"what randomness gives" and reads it correctly for the rest of the series.
Never spend DIM on an observed quantity.

Continuous data takes `saturated_magma()` with `punch()`, never raw magma.
Typography is Computer Modern (`CMU Serif`, mathtext `cm`), set globally at
import; `axes.unicode_minus` is off so minus signs render in the serif face.

## Composition

- **One claim per figure.** If two claims need two different geometries, that
  is two figures. Panels within a figure are the same claim seen from different
  sides.
- **Anatomy**: `figure(w, h, number, kicker, title, meta)` builds the header
  block — `FIGURE NN` kicker in gold, large serif title, hairline rule, muted
  meta line carrying the real numbers. The header reserves real estate in
  inches, so it stays the same physical size whatever the figure's aspect.
  `verdict(fig, text)` puts the conclusion on the kicker baseline,
  right-aligned, in red — one line, detail belongs in the section README.
- **Framing**: `panel_title()` on every panel, `style_axes()` on 2D axes,
  `fit3d()` on 3D axes, then always `frame_panels(fig)` before
  `fig.savefig(out, dpi=DPI, facecolor=BG)`. Every panel and the figure itself
  get a border; the border is what makes a multi-panel figure read as one
  object instead of a contact sheet. Margins are uniform (`MARGIN = 0.035`
  figure-fraction on every side, `PANEL_PAD = 0.014` inside each frame) — the
  header, the panels and the verdict all hang off the same left margin.
- **Fill the cell.** Hardcoded limits are the recurring bug in this repo: nine
  figures once drew themselves into a corner because every panel pinned
  `(-1, 1)` while the embedding spanned x -1.2..0.8. Take limits from the data.
  A *proportional* box aspect looks like the obvious fix and is a trap —
  matplotlib shrinks the axes to satisfy it, which mattes the sides and
  reintroduces the gap; proportion the figure so square cells fit, and let
  `zoom` eat the default 3D margin.
- **Legends earn their place.** If a legend is the only way to tell two series
  apart, the encoding is too weak — separate them by position or by panel
  first. A legend names what the geometry already distinguishes.
- **The meta line is part of the design.** It carries the measured quantities
  (counts, bandwidths, scores). A figure whose title claims something its meta
  line does not quantify is incomplete.
- **3D surfaces are figures, not screenshots.** A scalar field drawn as
  terrain gets the full anatomy: interpolate between grid nodes (bilinear,
  disclosed in the meta line — raw quads read as shards), hillshade for
  relief, labeled axes with muted furniture, a legend for every overlay line,
  and a box aspect/zoom that fills the frame cell so `frame_panels` frames
  content, not air. Orient the data's loud edge toward the camera. The first
  cut of 34's figure 04 violated all five; the rebuild is the reference.
- **Backend**: `matplotlib.use("Agg")` before pyplot; figures are files, never
  windows. Matplotlib is not a project dependency — run with
  `uv run --with matplotlib python scripts/<script>.py`.

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
`docs/assets/memory-field/README.md` records the one that happened; the
lesson is stamp-at-render, and when comparing figures across engine or data
changes, re-render everything under one version rather than mixing stamps
(`git log` is the arbiter when a stamp no longer resolves).
