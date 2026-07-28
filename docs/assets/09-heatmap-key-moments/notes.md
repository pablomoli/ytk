# Post material — measuring the timestamps against the crowd

Working notes for a post. Figures 01–03 tell the story in order; numbers and
quotables below. Everything here is reproducible from `raw.json` via
`scripts/heatmap_experiment.py` and `scripts/plot_heatmap_key_moments.py`.

## The setup

ytk pays Claude to generate `## Key Moments` — timestamped marks on every
ingested video, meant to be findable from memory later. Nobody had ever checked
whether they were any good, because there was nothing to check them against.

There is. YouTube publishes a **heatmap** in the yt-dlp info dict: 100 uniform
bins of normalized replay intensity, the same curve that draws the squiggle on
the scrubber. ytk has been fetching it on every single ingest since the
beginning and throwing it away.

That is a free, crowd-sourced attention signal on exactly the axis the generated
timestamps claim to mark. So the question stops being "do these look right" and
becomes a measurement.

## The result

| | mean replay intensity | lift over null |
|---|---|---|
| random offsets | 0.258 | — |
| **generated key moments** | **0.302** | **+0.044** |
| uploader's own chapters | 0.390 | +0.132 |

156 videos with a heatmap, 3,024 key moments, null = 200 uniform draws per
video against that video's own curve (seed 20260728).

**The timestamps are better than chance, on 76% of videos, and they reach about
a third of the lift a human uploader gets from the same curve.**

Both halves of that sentence matter. The first says the feature works — these
are not random marks. The second says it works considerably less well than a
person doing the same job by hand, which is the part that would never have
surfaced without a reference point.

## Quotables

> The null model is the whole experiment. "Key moments average 0.30 replay
> intensity" means nothing. 0.30 against a null of 0.26 drawn from the same
> curve means something, and 0.30 against a human's 0.39 on that same curve
> means something else again — it turns a pass/fail into a distance from a
> ceiling.

> Each video is scored against a null drawn from its own heatmap, so a video
> whose whole curve runs hot cannot inflate the result.

> We had been paying a model to approximate a signal we were already
> downloading and discarding.

## The actionable finding

Figure 03 was built to kill the result, not to support it — if lift tracked
video duration, the experiment would be measuring the shape of long-video
heatmaps rather than the quality of the timestamps.

It survived that check (**r = +0.02** against duration, flat) and turned up
something else on the way:

**lift falls as the number of marks rises — r = −0.15.**

Which is obvious once seen. Forty marks on a 78-minute video is a mark every two
minutes, approaching uniform coverage, and uniform coverage cannot beat a
uniform null by construction. Figure 02 shows it directly: the best video has 10
moments and +0.339, the worst has 21 and −0.061.

The enrichment prompt says "up to 8 timestamped moments." Notes in the corpus
carry 40. Whatever is or isn't enforcing that cap, the data says the cap was the
right instinct — **fewer, more selective marks should score better.**

## The caveat that belongs in the post

Videos without a heatmap are **not** a random sample. YouTube withholds the curve
on low-view videos, so 83 of 239 (35%) dropped out, and they dropped out for a
reason correlated with popularity. This measures the timestamps on the popular
half of the corpus. Whether generated moments are better or worse on obscure
videos is untested and unknowable by this method.

## What it argues for, in ytk

1. **Persist the heatmap** (#144). It is already fetched, already free, and it
   is demonstrably a better attention signal than what we generate.
2. **Persist chapters** (#144). Currently fetched, fed to the enrichment prompt,
   rendered in the terminal, and never written to the note — they only survive
   when an uploader happens to duplicate their timestamps into the description.
   They are the strongest signal measured here.
3. **Cap key moments harder.** The density correlation says selectivity is what
   is being lost.
4. A heatmap in the note also makes this experiment rerunnable per-video, which
   turns key-moment quality into something the enrichment eval can regress on
   rather than a one-off study.

## Figures

- `01-key-moments-vs-null.png` — the measurement: pooled distributions, the
  three-way per-video comparison, both effect sizes on one axis
- `02-worked-examples.png` — best / median / worst, the curve with the marks on it
- `03-artifact-checks.png` — lift vs duration, lift vs mark count, and coverage

## Sidecars

- `raw.json` — one record per video: heatmap values, key-moment offsets,
  chapters, duration, view count
- `results.json` — per-video scores and the pooled draws behind figure 01
