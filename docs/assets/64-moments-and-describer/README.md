# 64 — Moments, and a describer that sees the corpus

Drawn 2026-11-22. Section 63 left every video as one averaged point and the
measured look sorting only by kind of screen. Two steps here: cut each video
into its distinct looks with no model, then have a model describe real frames
of those looks, with and without the corpus in view. A pilot, 20 videos;
nothing was registered beforehand.

```bash
uv run python scripts/sprite_moments.py                       # 3 min, no model
uv run --with matplotlib python scripts/moments_figure.py
uv run python scripts/look_describer.py                       # 41 min: 111 frames pulled in 3.4 min, then 30 model calls
uv run --with matplotlib python scripts/describer_figure.py   # embeds 208 short texts locally
```

## 64.1 — Moments

![01](01-moments.png)

**What was measured.** The 95,852 tile vectors of section 63. Near-black
tiles are dropped by rule (mean brightness under 0.03 and spread under 0.02:
495 tiles). Within a video, tiles within cosine distance 0.22 of each other
(average link) are one **look**; an unbroken run of one look is a **moment**.

| | |
|---|---|
| looks | 8,585 |
| moments | 19,968 |
| looks per video | median 13, quartiles 6 and 26, largest 375 |
| videos holding a single look | 30 |

The threshold 0.22 is a first choice and was not tuned against anything. A
fight film study comes out as one look for its whole length.

## 64.2 — The describer pilot

![02](02-describer.png)

**The setup.** 20 videos: three families of near neighbors by what is shown
(fights, math animations, node-editor tutorials) and seven spread across the
corpus. For each video, one real frame per look for its nine largest looks,
pulled from the video at full resolution at that moment and handed to the
model untouched (111 frames; one fell back to a sprite tile). The model
(`claude-sonnet-5`, through the subscription) never sees a title. Per frame
it writes what is shown, how it looks with the subject removed, a named
lineage if there is one, a feel, and terms as `facet:term`.

- **Aware arm, 20 videos**: the vocabulary built so far with definitions and
  counts, plus, per frame, how its nearest already-described frames (tile
  vector cosine at least 0.70) were worded. Reuse a term when it fits; define
  any new one.
- **Blind arm, the first 10 of those videos**: the same frames, neither.

An earlier run on enlarged sprite tiles was stopped after six videos: the
describer was writing "video compression softness" about the enlargement.

**What came back.** 104 usable frames of 111; the model marked 7 as carrying
no look. 93 of the 104 name a lineage.

| on the same 10 videos, 59 frames | aware | blind |
|---|---|---|
| distinct terms | 106 | 239 |
| terms per frame | 5.3 | 5.8 |
| shared-term share, all pairs from different videos | 0.119 | 0.008 |
| shared-term share, the most alike sixth of pairs | 0.360 | 0.022 |
| distinct style terms | 4 | 36 |

Blind, nearly every term is new: two frames the image model finds most alike
share 2% of their terms, which is inside what dealing terms at random gives.
Aware, they share 36%, and agreement rises with how alike the frames are.
The owner's prediction, that the same thing would be worded differently
each time, is what the blind arm shows.

**Is the look text the subject again?** Neighbors among frames of other
videos, k = 10, 104 frames: the look text and the shown text agree on 0.408
of neighbors (shuffled 0.097), look text and the image model's frame vector
on 0.325, shown text and the frame vector on 0.360. So the look text follows
what is depicted about as much as anything here does. The pilot cannot say
how much of that is leakage, because its three families are frames that
both show the same thing and look the same.

**Limits.**

- Agreement is not correctness. The aware describer was shown its neighbors'
  terms, so it can also carry a wrong term forward. Nothing here scores a
  term against a human judgment.
- Reuse may cost specificity: the aware arm coined 4 style terms where the
  blind arm coined 36. Whether the 4 are the right merge or a collapse is
  not measured.
- Half the vocabulary is single-use (71 of 140 terms), and subject words
  still enter as look terms (a cage-fence backdrop, a forest green).
- One frame per look, nine looks per video, 20 videos, one run per arm. The
  arms ran in sequence on the same frames; no repeat to size run-to-run
  variation.

`results.json` holds the counts and the agreement scores. The frames, the
descriptions and the vocabulary live under `~/.ytk/describer`; the sheet of
frames beside their descriptions is written outside the repo.
