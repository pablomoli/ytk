# Post material — the geometry survives growth; the roads do not pave themselves

Working notes. Figures 01–04. The out-of-sample test of everything measured on
the frozen snapshot: the corpus grew 493 -> 568 (15%) between the freeze
(2026-07-28) and this capture, and every geometric claim was re-measured on
both, with the same code, in the same process.

Read-only on the freeze: `../10-tag-coherence/vectors.npz` is never written.
The fresh capture lives here as `vectors-fresh.npz` + `tags-fresh.json`.

## The question

Four claims underpin the interpolation work, all measured once, on one
snapshot. Growth is the cheapest falsification attempt available: if any of
them is an artifact of n=493, fifteen percent more data should move it.

## The findings

| claim | freeze (n=493) | fresh (n=568) | verdict |
|---|---|---|---|
| the cone: ‖mean‖ | 0.5104 | 0.5106 | holds; direction rotated 2.3 deg |
| participation ratio | 104.4 | 106.7 | still n-limited — no encoder ceiling found |
| tag coherence z | 69 tags | 69 shared + 2 new | r = 0.984, mean \|dz\| = 0.56 |
| fig-05 path support (min) | 0.502 / 0.520 | 0.510 / 0.520 | unchanged |

- **E1, plateau.** ‖mean‖ is flat in n from 256 onward (subsample curve, 20
  draws per size) and the axis direction moved 2.3 degrees. The offset is a
  property of the encoder and the content mix, not the sample. The
  falsification failed, which is what the interpolation machinery needed.
- **E2, participation ratio.** 104 was never a ceiling: 75 notes bought 2.3
  effective dimensions, and the PR-vs-n curve is decelerating (0.34/note at
  n=64-128 down to 0.04/note at the top) but not flat. At matched n=493 the
  fresh corpus measures 103.6 — the freeze value replicates exactly; the gap
  is pure n.
- **E3, tag stability.** Only boundary jitter: `python` (z 2.57 -> 1.96) and
  `rec` (1.94 -> 2.37) swapped sides of z=2, both hovering there already.
  Largest absolute mover is `creative-coding` (11.97 -> 9.74 while gaining 22
  notes), still unambiguously coherent. `career` and `mathematics` reached the
  6-note floor for the first time.
- **E4, path support.** The sobering one. 75 new notes moved the related
  path's minimum support by 0.008 and the unrelated path's by nothing.
  Density gains spread across the whole cone; none landed near these arcs.
  Decode-by-retrieval works exactly as well as before — and no better.
  Support was already above 0.50 everywhere, so nothing is lost; but organic
  growth at this rate is not what will improve a specific path.

## E5 — the path census (added same session)

The E4 caveat resolved: support along the slerp arc for every
nearest-neighbor pair (457) plus 500 random pairs, 39 interior stops each.

- **0 of 957 paths dip below the corpus background anywhere.** p5 of
  minimum support is 0.39 for both populations; medians 0.510 (nn) and
  0.493 (random). Random pairs are barely worse than chosen ones — the cone
  keeps everything decodable. No desert between the cities.
- **Min support falls with endpoint angle** (fig 05 right): longer roads
  sag, none break. The nn population shows a tight angle-support band;
  random pairs are diffuse around it.
- **Hubness is real but mild** (fig 06): 463 of 568 notes answer at least
  one stop; the top note serves 5.5% of paths, the top ten 12% of answers.
  Far from the winner-take-all hub mass that arXiv 2605.26575 finds driving
  cross-lingual retrieval asymmetry — but a design input for the path
  interface: dedupe stops per walk and down-weight habitual answerers.

## E6 — Haiku blend narration (blend-demo.md)

Smallest end-to-end slice of the path interface: slerp -> retrieve top-3 ->
`sdk.structured` merge, weighted by cosine, on the unrelated fig-05 pair.
The stops grade correctly from interview country (NeetCode, system design)
through a genuine mixed zone to the instagram-neuro side, and the
narrations stay grounded in the retrieved notes. One wrinkle surfaced:
t=0.75 retrieved the *same reel* as endpoint B under a second filename
(`rndyrbrts-2026-04-02-DWpSK4uDhIO` vs
`randyroberts-DWpSK4uDhIO-tribe-brain-heatmap`) — endpoint exclusion by
index misses duplicate ingestions, so the interface must dedupe stops by
content identity, not row index.

## Caveats

- **One growth step.** 493 -> 568 is a single before/after; the subsample
  curves borrow strength within the fresh corpus, but a second real capture
  later is the honest longitudinal point.
- **Same encoder throughout.** All of this is the v2 Qwen3/1024d epoch; a
  re-embed restarts every curve.
- **E4 is two paths.** The fig-05 pairs were kept for comparability, not
  swept. A corpus-wide path-support census (all pairs, or all
  nearest-neighbor pairs) is the obvious next measurement before concluding
  growth never densifies paths.
- **New null draws per snapshot.** z-scores were recomputed with fresh nulls
  on both sides (seed 20260804); freeze numbers here differ from
  `../10-tag-coherence/results.json` in the third decimal for that reason,
  and that is the point — nothing was copied forward.

## Figures

- `01-plateau.png` — ‖mean‖ vs n with isotropic reference; freeze/fresh cone stats side by side
- `02-pr-growth.png` — participation ratio vs n against the n-1 cap, per-segment growth rates
- `03-tag-stability.png` — per-tag z, freeze vs fresh, with the threshold-crossers named
- `04-path-support.png` — the fig-05 slerp arcs re-measured on the denser corpus
- `05-path-census.png` — min-support distributions and the angle-support relation
- `06-hubness.png` — concentration curve of stop answerers, the ten busiest notes

## Sidecar

- `results.json` — E1-E4, stamped with seed and commit
- `census.json` — E5, per-path min/median support, angles, hub counts
- `blend-demo.md` — E6, three narrated stops with retrieval evidence
- `vectors-fresh.npz`, `tags-fresh.json` — the 2026-08-02 capture (568 notes)

## Render

```bash
uv run python scripts/growth_experiments.py harvest   # touches Chroma + vault, read-only
uv run python scripts/growth_experiments.py analyze
uv run python scripts/growth_experiments.py census
uv run --with matplotlib python scripts/growth_experiments.py plot
uv run python scripts/path_blend_demo.py              # 3 Haiku calls
```
