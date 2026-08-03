# Section 21 — road-network geometry: the digon shows up, the roundabout dies

Registered in `../18-sae-fingerprints/preregistration.md` (section 21) before
any measurement. Instruments transplanted from Toy Models of Superposition
(Elhage et al. 2022) and its SAE-scale follow-up (Li et al. 2024, arXiv
2410.19750), both ingested to the vault. Inherits: centred space for geometry
(section 15), raw-cosine retrieval for roads (19.1), sum pooling + mass
presence (18), 45 large-tag-pair centroid roads, stops=9, k=3.

## Scoreboard

| block | prediction | verdict |
|---|---|---|
| 21.1a | centroids non-orthogonal vs isotropic null | **CONFIRMED** — mean abs cos 0.308 vs null p95 0.030 |
| 21.1b | more spread than subset-centroid null | **CONFIRMED** — spread 1.281 vs null p95 0.545 |
| 21.1c | participation ratio <= 5 | **CONFIRMED** — 4.62 (iso p5 9.88, subset p5 8.82) |
| 21.2a1 | decoder rows non-isotropic | **CONFIRMED** — mean abs cos 0.043 vs null p95 0.018 |
| 21.2a2 | no polytope plateaus | **FAILED — the headline.** 12 features on the 1/2 plateau vs null p95 of 0 |
| 21.2b | no antipodal tag pair | **CONFIRMED** — min pair cos -0.466 |
| 21.3a | top-10 notes >= 25% of stop slots | **CONFIRMED, overshot** — 89%, and only 19 distinct notes are ever retrieved |
| 21.3b | >= 3 true crossings (deg >= 4, angle >= 60) | **CONFIRMED** — 16, max angles up to 90 |
| 21.4 | handover concentration | **KILLED by registered criterion** — 31/45 single-crossing roads < 35 |

## 21.2 — the digon geometry, against the registration

The skeptical registration lost, and the standing rules make that the
finding: twelve of the 31 always-on cone features sit within 0.02 of
dimensionality exactly 1/2, and they resolve into **six antipodal decoder
pairs** at cos -0.992..-0.960, with a seventh pair at -0.926 just outside
the plateau tolerance. The isotropic null produces zero plateau hits at p95.
This is the digon — the first geometry in the toy paper's sequence —
realized in production Gemma-Scope decoders among features that fire on
every note in this corpus.

Auto-names of the pairs (hypotheses, unprobed, per the standing caveat):

| pair | cos | names |
|---|---|---|
| 6631 / 8684 | -0.992 | proper nouns / technical jargon and programming terms |
| 5052 / 8366 | -0.990 | beginning of a document or section / verbs, media-related forms |
| 1530 / 5533 | -0.974 | inventions and scientific terms / medical and biological testing |
| 1692 / 10931 | -0.971 | legal and statutory terminology / programming keywords and parameters |
| 4784 / 5328 | -0.968 | scientific-technical descriptions / legal and statistical terms |
| 10419 / 14881 | -0.960 | scientific technical terms / lubrication and mechanical properties |
| 549 / 10640 | -0.926 | programming and code structure / critiques and evaluations in research |

Reading, offered as hypothesis: an antipodal pair of always-on features is a
**signed axis** — the two features jointly encode one bidirectional residual
direction, each firing for one sign of it. That would mean the cone carries
at least six axes, not 31 independent directions. Token-level probing of both
halves of one pair is the natural follow-up before believing any name.

## 21.3 — intersections, with the honest caveat

The concentration prediction did not just clear its bar, it embarrassed it:
across 1215 stop slots on 45 roads, **19 notes** are ever retrieved, and the
top note (the Obsidian + Claude Code workflow video) serves 37 of 45 roads.
The census prior (12% on note-pair arcs) badly underestimated tag roads,
which run centroid-to-centroid through the densest country.

Caveat recorded against my own prediction (b): the registered 60-degree bar
sits *below* the measured null median of 69.2 degrees — near-orthogonal
tangents are the high-dimensional default, so a wide angle is not by itself
remarkable. What the 16 true crossings establish is co-retrieval from
genuinely different directions, not an unusual angle. The interchange list,
not the angles, is the usable output.

## 21.4 — the kill, and what it localizes to

31 of 45 roads cross the 0.5 share line exactly once; the registration
demanded 35. Post-hoc diagnosis (marked as such): 13 of the 14 failures
never cross because they start B-dominant at t=0 — the exclusive-mass
baseline is asymmetric for those tag pairs — and one crosses twice. The
18.5/20.1 monotone-handover result was real on its two measured roads but
its *single-crossing* premise does not generalize to all pairs, so the
roundabout construct as registered is void. A share-renormalized definition
might survive; that would be a new registration, not a patch to this one.

## 21.1 + 21.5 — the constellation and the atlas

Ten interests span an effective ~4.6 dimensions (of a possible 10) with
pairwise structure far beyond both nulls in both directions — real
attractions (learning/education +0.81) and real aversions (cool-vis/research
-0.47, shy of antipodal). Deviation recorded: tag sizes sum to 1211 > 568
notes, so the subset null drew subsets independently rather than disjointly.
Exploratory parallelogram probe (descriptive only): best analogy
cool-vis - research ~ -(ai - creative-coding), cos -0.91.

Fig 05 is the atlas: 45 roads over the centred corpus in the centroid-PCA
basis, stroke by min-support, the six intersections and top interchanges
marked. City markers use the arcs' own construction (centred raw centroids)
so roads anchor exactly on their endpoints.

## Consequence for the hub road UI

With 19 answering notes across all 45 tag roads, a tag-road overlay would
funnel every itinerary through the same few interchanges. The shipped v1
(note-to-note roads, feature/map-road branch) is the right surface;
any future multi-road view should dedup stops by interchange before
rendering.

## Figures

- `01-constellation.png` — pairwise cosines, spectrum, and both nulls
- `02-polytope-probe.png` — the 1/2 plateau, the antipodal pairs, no tag antipodes
- `03-intersections.png` — 19 notes carry 1215 slots; the interchange list
- `04-roundabouts.png` — every handover curve; the kill criterion firing
- `05-the-map.png` — the road atlas

## Render

```bash
uv run --with sae-lens python scripts/road_geometry.py wdec   # once, cached
uv run --with matplotlib python scripts/road_geometry.py
```
