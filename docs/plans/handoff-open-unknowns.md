# Handoff: the open unknowns

Written 2026-07-25 against master `49bef92`. Self-contained: reads only durable
state (the repo, GitHub issues, `~/.ytk/`).

You are picking this up cold. The work below is **investigation, not delivery**.
Several items here have already been "explained" once by a confident guess that
turned out to be wrong, so the standard is higher than usual: a claim counts
only when a measurement you ran disagrees with the alternative.

---

## Start here

```bash
cd ~/Developer/ytk
git fetch origin master && git log --oneline -1 origin/master   # expect 49bef92 or later
wt switch -c investigate-unknowns          # ALWAYS wt, never raw git worktree
```

`wt switch -c` branches from your **local** default branch. Local master went
stale earlier in this repo's history and cost a rebase — confirm before you
start:

```bash
git -C <worktree> merge-base --is-ancestor origin/master HEAD && echo OK
```

Then, in the worktree:

```bash
uv sync --extra dev --extra lab    # BOTH extras; --extra lab alone drops dev deps
cd web && vp install               # fresh worktrees have no node_modules
```

Baseline before touching anything, so you can tell your breakage from inherited
breakage:

```bash
cd web && vp check && npm test     # expect 0 errors, 172 passed
```

---

## What "verified" has to mean here

This session produced four confident, wrong measurements in a row on one
question. Each looked fine in isolation. The failures, so you can recognise them:

1. Counted bytes of **compressed PNG** as a proxy for lit pixels. Meaningless.
2. Counted pixels in a screenshot region that included the **DOM chrome**
   overlapping the canvas, which dwarfed the signal being measured.
3. Diffed frames while the **flow-pulse animation was running**, so the diff
   measured animation, not the change under test.
4. Captured at a viewport/DPR where `clamp(size*zoom/depth*dpr, 1.8, 26.*dpr)`
   renders points sub-pixel, so the thing being measured was **not on screen at
   all** — and it was invisible on unmodified master too, which is what finally
   proved the harness rather than the feature was broken.

The habits that would have caught each:

- **Measure a known-real signal through the same pipeline first.** The theme-axis
  null only became interpretable once a ground-truth partition (source platform)
  was scored the same way: 0.65 sd, against 1.00 sd for the thing under test.
  Without that anchor, 1.00 sd reads as "barely above chance".
- **Run the null/control arm on unmodified master.** Twice this session the
  answer to "did I break this?" was "master does it too".
- **A difference is not a direction.** "Frames differ" is satisfied by a camera
  still easing. Assert what should be *identical* as well as what should differ.
- **Never report a number whose units you cannot name.**

---

## The unknowns

Ranked by (value of the answer) x (tractability). Do them in order unless one
blocks you — with two exceptions:

- **#2 (the suite hang) comes first.** Everything you conclude about the Python
  side is unverifiable until a full run can complete.
- **#7 is not an unknown, it is a known-broken figure**, and it is the public
  evidence for an issue that has already merged. It has a diagnosed cause and a
  bounded fix, so it is cheap. Do it early rather than last.

### 1. The bloom model over-predicts the GPU by ~1.8x — cause unknown

**Status:** open, one hypothesis already refuted.

`labs/bloom_tuning.py` runs the same arithmetic in numpy that the shader chain
runs on the GPU. The model says the composite adds **0.76%** light; the GPU
measurably adds **0.43%**. Witness: `docs/assets/05-bloom/01-model-vs-gpu.png`,
error structure in `02-error-structure.png`.

**Already tried and REFUTED — do not re-run this:** premultiplied alpha. It was
implemented, and the measured error was *identical* afterwards. Commit `ac9630a`
("correct the record — the alpha change did not explain the gap") exists
specifically so nobody burns a day on it twice.

**Also parked by decision:** the marimo notebook is unreliable and must not be
tuned against. If bloom needs retuning, do it against the GPU.

Candidates worth measuring, roughly in order of cheapness:

- **Texture format / precision.** The bloom targets are half or byte textures;
  numpy is float64. Quantisation at 8 bits per channel across a downsample plus
  two blur passes plus a composite could plausibly eat light. Measure: render a
  known constant patch, read it back with `gl.readPixels`, compare to the model
  at the same bit depth.
- **The downsample ratio.** `bloomTargets()` picks `sw, sh`. If the model assumes
  full resolution and the GPU blurs at half, the energy per output pixel differs
  by a factor that is *suspiciously close to* the observed ratio. Check what
  `sw/sh` actually are at the DPR the measurement ran at.
- **`LINEAR` filtering on upsample.** The comment says LINEAR was chosen so the
  bloom upsamples smoothly. Bilinear on upsample redistributes energy; the numpy
  model may be doing nearest.
- **sRGB / gamma.** If the framebuffer is sRGB-encoded and numpy sums in linear,
  the discrepancy is a gamma curve, not a bug. 0.43 vs 0.76 is not obviously
  `x^2.2`, but check before dismissing.

**What counts as an answer:** a change to the model (not the shader) that makes
prediction and measurement agree within noise, *and* an explanation of why, *and*
a regenerated `01-model-vs-gpu.png` showing the agreement. If the cause turns out
to be a genuine shader bug, the fix belongs in a separate commit from the
investigation.

**What counts as a non-answer:** tuning a constant until the numbers match.

---

### 2. #120 — `test_hub.py` hangs; there is no green full-suite signal

**Status:** cause partially known, scope unknown. **Do this early** — everything
else you conclude about the Python side rests on it.

`uv run pytest tests/` never completes. It wedges inside `tests/test_hub.py` and
sits until killed. Reproduced on an **unmodified checkout at `90e60c6`**, so it
is not caused by any recent branch.

Known:
- `test_refresh_sources_pulls_instagram_and_youtube` reaches out to Instagram and
  YouTube for real, and is the last test to print under `-v` before the stall.
- **Deselecting that one test is not sufficient** — the file still wedges. There
  is more than one network-bound test in there. Nobody has enumerated them.
- Every other test file passes. A per-file sweep with a 120s cap over ~90 files
  came back clean except this one.

Separately, when the full suite ran *concurrently with other torch-loading work*,
it died with `Fatal Python error: Aborted` inside torch/SigLIP. That did not
reproduce when run alone and looks like memory pressure on a 16 GB machine, not a
logic fault — but it is unconfirmed, and it is a second reason the suite has
never been seen green.

**Method:** run `pytest tests/test_hub.py -v` and record where it stalls; kill;
deselect; repeat, until the file completes. That enumerates every offender.

**What counts as an answer:** `uv run pytest tests/ -q` completes, with the
network-dependent tests marked (`@pytest.mark.network` or similar) and excluded
by default the way `-m "not eval"` already excludes the eval gate, plus
`pytest-timeout` with a per-test cap so a future hang fails loudly in seconds.
Report the count of tests you moved behind the marker.

---

### 3. The eval gate has not run since the #105 re-embed — and I said it had

**Status:** unrun. This is a correction, not a discovery.

`eval/retrieval/baseline.json` was last stamped at `dc5886f` ("re-stamp the
retrieval baseline after the #105 re-embed"). It was **not** run during the #106
work, despite that task being marked complete. #106's own acceptance criteria
call for it.

#106 changed `THEME_FLOOR` in `scripts/build_map.py` and the domain-labelling
path. Neither is on the retrieval path, so the expectation is that the gate is
green and this is a formality. **Verify rather than assume:**

```bash
uv run ytk eval
```

If it fails, that is a real finding and it means something about the store moved
that nobody has accounted for. Do not `--update-baseline` to make it pass —
find out why first.

---

### 4. Downstream figures carried stale provenance labels — resolved, verify it held

**Status:** fixed 2026-07-25, worth a glance rather than a re-run.

#106 changed the map's domain axis, and `docs/assets/01-fog/` and
`docs/assets/02-picking/` both render domain labels. They were **not**
regenerated when #106 merged, despite that task being reported complete — they
kept showing `niloc` / `usf` / `config` / `other` for most of a day. Both have
since been regenerated.

Only `02-picking/03-scan-agreement.png` actually changed in that series; the
other three are models and carry no domain labels. If you re-run anything here,
expect the same and do not read an unchanged file as a failed run:

```bash
uv run --with matplotlib --with numpy python scripts/plot_assets.py --refresh
uv run --with matplotlib --with numpy python scripts/plot_picking.py
```

`plot_picking.py` reads `measured.json`, which came from a real browser run. If
a figure needs that re-measured, say so rather than quietly plotting stale
numbers — `scripts/measure_picking.py` regenerates it against a live hub.

Trap: `scripts/plot_domains.py` deliberately freezes its "before" panel in
`docs/assets/06-semantic-domains/counts.json`, because `before_counts()` reads
the live `~/.ytk/map.json` which *is* the new axis now. Do not "fix" that freeze.

---

### 5. Is the interest-theme axis actually meaningful?

**Status:** genuinely open, and it matters because #106 built on it.

The matched null test (centre on the content mean, draw the null from content
only) puts the theme assignment **1.00 sd** above chance. For scale, grouping the
same notes by **source platform** — ground truth, since it is metadata rather
than inferred — scores **0.65 sd** on the identical test. So themes clear a
partition that is definitionally real, which is why the axis was kept.

But 1.00 sd is not a lot, and the four arms in
`docs/assets/06-semantic-domains/02-theme-floor-null.png` range from **0.36 to
4.50 sd on identical data**, differing only in the null's pool and centring. That
spread is itself the finding, and it means the "1.00" is one modelling choice
among several defensible ones.

Open questions, none answered:
- Does the separation hold under a **different encoder**? The corpus is on
  Qwen3/1024d since 07-17.
- Does it hold **within** a single source platform, which would rule out the
  possibility that themes are partly re-deriving platform?
- The map readout prints **`sil -0.00`** — the domains have essentially zero
  silhouette in the 2D layout. Trustworthiness is 0.97, so the projection is
  faithful; the domains simply may not be separated *in the embedding*. Is the
  label axis describing structure that exists, or painting names onto a
  continuum? Prior work in this repo found `epicmap` has no reproducible flat
  partition but that coarse dendrogram geometry does reproduce — gradients, not
  clusters. That result should inform this.

**What counts as an answer:** a figure with the null construction stated
explicitly, a ground-truth anchor scored the same way, and 20+ seeds with paired
intervals. Flat ARI on a single seed is not evidence; a two-seed "win" has
already been shown to be noise in this repo.

---

### 6. Why do whole categories carry no dates?

**Status:** measured, unexplained.

`docs/assets/07-time-machine/01-date-distribution.png`, third panel. Date coverage
is 95.6% overall but is **structurally** biased, not randomly sparse:

| category | dated | | category | dated |
|---|---|---|---|---|
| memory | 98% | | project-note | **0 / 71** |
| instagram | 100% | | pinterest | **0 / 5** |
| youtube | 99% | | reddit | **0 / 4** |
| memo, tiktok | 100% | | web, screenshots | **0%** |
| | | | vault | 37% |
| | | | journal | 20% |

The time machine currently exempts undated notes (`birth = -1`, always visible)
precisely because assigning them `t=0` would fabricate a history for one class of
note and not another. That is a defensible default, not a fix.

Unknown: whether these dates are *absent* or merely *not extracted*. `project-note`
at exactly 0/71 smells like a parser gap rather than 71 genuinely undated files —
`build_map.py` derives memory dates from a `DATE_RE` search over `doc_id` and
`source_path`, and project notes may simply not match that shape. Check the raw
files before concluding anything.

Related and already filed: **#118**, 136 legacy flat memory atoms under
`memories/` whose project is recoverable from the filename but is dropped by the
`i + 1 >= len(parts) - 1` guard in `project_from_path`. That fix is **not** a
drive-by: `project_from_path` is imported by `scripts/grove_lab/buckets.py`, and
the grove's tree topology is cached and expected to grow incrementally rather
than reshuffle. Any change there needs a before/after count of grove membership,
reported explicitly.

---

### 7. Figure 01 of the semantic-domains series is wrong, and it is the evidence for a merged issue

**Status:** confirmed defect, cause diagnosed, not fixed. Reported by the user
on sight, which is itself the lesson — nobody re-read the figure after the
config it reads changed underneath it.

`docs/assets/06-semantic-domains/01-before-after-histogram.png` is the witness
that justified #106. It currently **contradicts what #106 actually shipped**.
Three separate problems, compounding:

**a. Panels 2 and 3 are the same chart with different titles.**

They are meant to contrast "hackathons left unplaced" against "hackathons as
their own bucket". `after_counts(with_hackathons: bool)` reads the proposal at
`docs/plans/106-buckets-proposal.yaml` and *appends* a hackathons bucket when the
flag is true. That worked when the proposal had no such bucket. After the user
approved adding one, the proposal contains it permanently — so the `False` arm no
longer excludes anything, and both panels render the bucketed case.

The `True` arm is worse than redundant: it appends a **second** `hackathons`
bucket, and because `assign()` is first-match-wins the duplicate matches nothing.
Panel 3 carries a phantom zero-height `hackathons` row. `counts.json` shows the
label twice.

**b. The totals do not reconcile, so every percentage is suspect.**

```
before           sum 4067   9 rows
after_excluded   sum 4650  11 rows
after_bucketed   sum 4650  12 rows      corpus total recorded as 4650
```

The `before` panel is the live map's 4067 points, but its percentages are divided
by 4650. Worse, the live map reports `unplaced 662` and `hackathons 620` while
the figure claims `unplaced 1237`. **The figure disagrees with the shipped map.**
4650 vs the 4068 measured earlier in the session is unexplained — find out
whether the corpus grew, whether `resolve_notes()`'s dedupe stopped firing, or
whether the two arms are being summed into one denominator, before trusting any
number in that file.

**c. No legend, and the styling does not carry its own meaning.**

The colour encoding — gold = grouped by topic, blue = grouped by path or project
slug, grey = other/unplaced — exists only as a sentence in the header meta. The
panels have no legend, so the figure cannot be read on its own, which defeats the
point of a checkpoint meant to survive into a writeup. Panel 3's title also
asserts "84% placed" against data showing 1237 unplaced.

**Method:** fix the data first, then the styling — a pretty chart of wrong
numbers is worse than an ugly one. Decide whether the two "after" arms are still
worth contrasting at all now that the hackathons question is settled; if not, the
honest figure is before-vs-after with one after panel, and the variant comparison
becomes a sentence.

**What counts as an answer:** the panels differ, the sums reconcile against a
stated corpus size, the numbers match `~/.ytk/map.json`, and a legend makes the
colour encoding readable without the caption. Regenerate with `--refresh`, then
**open the PNG and read it** rather than trusting the exit code.

**Trap while fixing:** `before_counts()` reads the live `~/.ytk/map.json`, which
*is* the bucket axis now, so the "before" panel is deliberately frozen in
`counts.json` (see item 4). Do not unfreeze it to make the sums line up — the
frozen values are the only surviving record of the provenance axis.

---

## Traps that will cost you time

- **Shader linking is a runtime event.** `tsc`, the linter and 172 tests all
  passed a program the GPU refused to link, and the map rendered "Something went
  wrong!" for a commit. Verify in a browser: `scripts/smoke_map.py --base <url>`
  and `scripts/shoot_flow_pulses.py --url <url>`.
- **The point program sits on WebGL1's 16-attribute ceiling.** A 17th attribute
  does not degrade, it fails to *compile* ("Too many attributes"). `id` and
  `birth` already share one `vec2`. Any new per-vertex data needs the same
  packing, or WebGL2.
- **Uniforms must follow a `useProgram`.** Fixed in `a4983cf`, but the shape
  recurs: `INVALID_OPERATION: location is not from the associated program` in the
  console is a real defect, not noise. It was dismissed as harmless for hours
  because master had it too — *pre-existing* and *harmless* are different claims.
- **`--sweep` now reshapes the map.** It chooses UMAP params by silhouette
  computed on the domain labels, which #106 changed. The default build path is
  fixed-param and safe. Do not add `--sweep` to a rebuild casually.
- **Reduce motion is ON at the OS level on this machine.** Use `?motion=on` to
  override, `?bloom=off` to skip the post chain.
- **The hub serves the installed package, not the worktree.** A restart alone is
  not enough: `uv tool install --reinstall .` then
  `launchctl kickstart -k gui/501/com.ytk.hub`. Check
  `curl -s localhost:6969/api/ingest/status` first and do not restart mid-job.
- **`rolldown` externalises unresolved imports and still exits 0**, so a `dist`
  built without `web/node_modules` ships looking fine and fails in the browser.
  Install first; afterwards grep the bundle for external imports.
- **Do not `git stash`** — parallel sessions run in this repo and stash scoops
  other sessions' WIP. Add explicit paths.
- **Start every command with `cd <worktree> &&`;** bash cwd drifts after `cd web`.
- Never push to master. Never add yourself as a commit co-author.

---

## Rules of engagement

- **Go slowly.** Every item above is a question, not a ticket. Finishing fast is
  worth nothing here; the failure mode this doc exists to prevent is a confident
  wrong answer.
- **One finding per commit**, with the measurement in the message.
- **Record refutations.** `ac9630a` is the model: a commit whose entire purpose is
  to say "this explanation was tested and it is wrong". A refuted hypothesis that
  stays written down is worth more than an unrecorded confirmation.
- **If a measurement surprises you, suspect the measurement first.** Four of the
  five surprises in the last session were instrument error.
- **Say what you did not verify.** The two items above marked "also mis-marked
  done" exist because a task was reported complete without being run. If you run
  out of time, an honest boundary is a deliverable.
