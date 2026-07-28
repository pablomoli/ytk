# Post material — do your tags mean anything?

Working notes. Figures 01–08 in order. Everything reproducible from `vectors.npz`
via `scripts/tag_coherence.py` and `scripts/plot_tag_coherence.py`.

Read-only experiment: it reads note frontmatter and calls Chroma `get()`. Nothing
was written to the vault.

## The setup

Every ingested note gets `interest_tags` from enrichment. 974 distinct ones have
accumulated across 493 notes. Issue #37 says enrichment "mis-tags non-technical
content with canonical vocab" — a suspicion nobody had tested, because there was
no way to test it.

There is one. If a tag names a real category, the notes carrying it should sit
near each other in embedding space. So: mean pairwise cosine similarity within
each tag, against **a null of same-size random note sets**.

The size matching is the whole trick. A 6-note tag looks cohesive by accident far
more easily than a 125-note tag, so raw similarity is not comparable across tags.
The z-score against a size-matched null is.

## The result

**58 of 69 scorable tags cohere beyond z=2. Eleven do not.** The eleven are not
random — they are one specific kind of tag.

| tag | n | z |
|---|---|---|
| ai-coding | 49 | **+17.4** |
| ai-agents | 48 | +17.2 |
| claude-code | 31 | +15.5 |
| ai | 91 | +13.0 |
| creative-coding | 92 | +11.7 |
| … | | |
| learning | 131 | −0.5 |
| show-rec | 9 | −0.7 |
| video-essay | 85 | −1.0 |
| **reference** | **125** | **−3.4** |

## The finding

The failures split into exactly two families, and neither is about topic:

**Format labels** — `video-essay`, `show-rec`, `book-rec`, `movie-rec`, `rec`.
These describe the *container*. `video-essay` spans biological computing, Jon
Jones vs Adesanya, game lore, vinyl vs Spotify, and GPT-5.6. All genuinely video
essays. Nothing else in common.

**Utility labels** — `reference`, `learning`, `education`. These describe *your
relationship to the note*. `reference` is applied to AWS architecture, shader art,
SQLite internals, dinosaur extinction, gimbal calibration, a 17th-century book on
witchcraft, and about a hundred Instagram posts.

> `reference` scores **z = −3.4**. Not merely uncorrelated — **anti**-correlated.
> Two notes that share the tag are *less* alike than two notes drawn at random.

That is the sharpest thing in the experiment. It happens because `reference`
means "I might come back to this," which is a judgment about the note's *use*,
and it gets applied evenly across every subject in the corpus — so it spans the
space more uniformly than a random draw does. Embeddings encode aboutness. A tag
that isn't about aboutness scores below chance.

**`physics` (n=56, z=−0.1) is issue #37's exact symptom.** It covers EMP rifles,
Blender animation, quantitative finance, Maxwell's equations, puffin robots, and
brain criticality. Canonical vocabulary applied to anything science-adjacent.

## Quotables

> A tag that fails isn't a tag that clusters badly. It's a tag that describes the
> reader instead of the text.

> 974 tags for 493 notes, and 76% of them are used exactly once. A tag used once
> is a caption, not a category.

> Four labels, one region: ai-coding, ai-agents, claude-code and developer-tools
> all sit above 0.97 centroid similarity with each other, against a corpus median
> of 0.70.

## Actionable, in ytk

1. **Split the vocabulary by kind.** Topic tags belong in the embedded surface;
   format and utility labels are real and useful metadata that should live in a
   *separate* frontmatter field, not compete as topics. `reference` is not a bad
   label — it is a bad *topic*.
2. **Merge the near-duplicates** into `~/.ytk/tag-aliases.yaml`, which already
   exists for exactly this. The top pairs are in figure 03; `ai-coding` /
   `ai-agents` / `claude-code` / `developer-tools` is the biggest cluster.
3. **`physics` needs the #37 treatment** — it is the clearest case of canonical
   vocab spreading past its meaning.
4. **The long tail is mostly noise.** 741 single-use tags cost prompt tokens on
   every enrichment and buy nothing retrievable.

## Caveats, stated plainly

- **This measures embedding coherence, not correctness.** A tag can be perfectly
  accurate and still score low if the thing it names isn't what embeddings
  encode. `video-essay` is not *wrong* on any note carrying it.
- **69 of 974 tags were scorable.** The cutoff is 6 notes; below that the score
  is dominated by which notes rather than which tag.
- **Multi-label confound.** Notes carry 7.3 tags on average, so tags that
  co-occur inflate each other's apparent coherence. The `ai` family is genuinely
  entangled this way — four labels on largely the same notes.
- **One corpus, one encoder.** These z-scores are specific to the v2 Qwen3/1024d
  epoch. A re-embedding could move them, and the experiment should be rerun if
  the encoder changes.

## A second, independent measure agrees

Cohesion is computed on centroids. Neighbour purity is computed on nearest
neighbours — for every note carrying a tag, what fraction of its 10 nearest
neighbours also carry it, minus what random neighbours would give. Different
statistic, different failure modes, same corpus.

**They correlate at r = +0.71** (figure 07). `touchdesigner` and `blender` top the
purity ranking; `reference` and `game-dev` sit at or below zero. Two ways of
asking the question, one answer.

## Where the vocabulary differs by source

The mosaic (figure 08) is a chi-square over tag applications by source:
**chi-square 154 on 26 dof**, so the vocabulary is emphatically not source-neutral.
The largest residuals are `video-essay` over-applied to YouTube (residual ≈ +6)
and `build-idea` over-applied to Instagram.

That is the shape of issue #37 — but it is not proof of mis-tagging. A tagger
assigning topics purely from content would *also* differ by source, because the
sources genuinely differ. The mosaic localizes where to look, nothing more.

## Figures

- `01-tag-verdict.png` — all 69 scorable tags ranked by z against their own null
- `02-mechanism.png` — the similarity distributions behind three passes and three failures
- `03-vocabulary.png` — rank-frequency of the whole vocabulary, and the 16 most redundant pairs
- `04-structure.png` — the same similarity matrix seriated by average-linkage clustering, with dendrogram. Ranked by z it looked uniform; clustered, the blocks are obvious
- `05-neighbourhood.png` — every tag placed by MDS on its actual similarities. Generic tags at the centre, specific tags at the rim
- `06-sprayed-or-clustered.png` — UMAP of all 493 notes, twice, highlighting the best and worst tag. The picture of z = −3.4
- `07-retrieval.png` — neighbour purity, and its agreement with cohesion
- `08-mosaic.png` — tag vocabulary by source, tiles area-proportional, coloured by chi-square residual

## Sidecars

- `vectors.npz` — 493 unit-normed note embeddings
- `tags.json` — per-note labels, titles, source type
- `results.json` — per-tag scores, nulls, and the full centroid overlap matrix
