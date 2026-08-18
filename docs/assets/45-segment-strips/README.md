# 45 — Segment strips (rung 4 of #183)

**Question.** The epic flagged this rung as the likeliest to hit a wall:
a document-trained SAE encoding segment vectors is, on paper, a distribution
shift. Do per-video segment codes aggregate back to the video's document
code, and does segment order carry signal — or is a strip just noise with a
palette?

**Correction to the premise, first.** The SAE was not document-trained:
11,412 of its 16,483 training vectors are segments (rung 0's inventory).
The wall the epic braced for was unlikely by construction — but the gates
still had to be run, and the numbers published.

**Data.** The s0 acts cache (314 videos with a document code and >= 8
ordered segments), computed by `experiments/sae_qwen/segment_strips.py`;
the protagonist's 18 segments encoded live from Chroma (the video postdates
the cache). Rendered by `scripts/plot_segment_strips.py`; sidecars
`strips.json` / `strips.npz`.

## Findings

**Gate 1 — segments add up (figure 01, left).** Median cosine between a
video's mean segment code and its own document code: 0.67, against 0.02
when every document is paired with another video's segments; only 18/314
matched pairs fall inside the null's reach. Aggregation is valid.

**Gate 2 — order is signal (figure 01, right).** Mean lag-1 autocorrelation
of each video's top-8 latent series: median 0.28 in real order vs -0.04
under 100 per-video order shuffles; 307/314 videos sit above their own
null. Concepts run in stretches, so a strip is a reading order, not an
arrangement of ink.

**The protagonist strip (figure 02).** The AlexNet video's segment-level
vocabulary is the play-by-play, not the summary: #1206 "neural network
mechanics and mathematics", #258 "images beat text for language models",
#114 "neuron activation interpretability", #729 "residual connections in
transformer architecture" — while its document code led with #1597's
educational register (section 42). The document sees the lecture; the
segments see the material. Its own autocorrelation is 0.13 vs a -0.05
shuffle null — positive but modest at 18 segments, disclosed as such; the
population claim rests on figure 01.

## Figures

- `01-the-license.png` — both gates as distributions against their nulls,
  protagonist marked CYAN.
- `02-protagonist-strip.png` — the strip in real order over one shuffle
  draw of the same values.
