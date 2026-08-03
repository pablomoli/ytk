# Query spaces — the highway and the bridges that were not missing

Pre-registered in `../18-sae-fingerprints/preregistration.md` (section 20,
detailed blocks committed before running). 20.1 and 20.4 ran this session;
20.2 (barycentric blends) and 20.3 (extrapolation) are registered and
pending. Inherits: cosine retrieval (19.1's verdict), content-identity
dedup, sum pooling, mass presence, auto-names as probed hypotheses.

## 20.1 — the highway: ai-agents -> machine-learning

The registered endpoint rule resolved to A = ai-agents (fresh z 19.0) and
B = machine-learning (z 11.7, centroid cos 0.862 — the first tag under
the 0.9161 threshold). Honest note on the rule: the threshold was
permissive enough that both endpoints are tech-side tags; a cross-domain
highway (ai -> creative-coding, cos 0.80) would be an unregistered
appendix, not a substitute.

Verdicts, sub-prediction by sub-prediction:

- **(a) CONFIRMED, overwhelmingly**: minimum stop support 0.750 vs
  background 0.259 — the highway runs through the densest country in the
  corpus.
- **(b) CONFIRMED**: vocabulary handover perfectly monotone, rho = -1.0
  (chance p95 0.63). Lanes: git commands, software capabilities and
  automated testing drain; tensor operations, neural networks, loss
  functions fill; the cone register persists. (One B-lane auto-name,
  "election integrity" #13860, is another polysemantic mislabel per the
  standing caveat.)
- **(c) FAILED**: zero bridge stops — every stop's top note carries an
  endpoint tag. Between two large coherent regions the road is paved
  entirely with their own notes: the regions abut, with no third-party
  territory between them. The bridge prediction assumed sparse borders;
  the corpus has dense ones.

The itinerary is itself the artifact: Obsidian+Claude-Code agent tooling
-> Opus-vs-Fable testing -> code reel -> how GPT/Claude/Gemini are
actually trained. A hub path view rendering exactly this would need no
model call.

## 20.4 — missing bridges: FAILED, and the failure is the finding

Registered: at least 2 of the 45 large-tag pairs combine individually
coherent tags with mean midpoint support below the all-pairs median.
Measured: **1** (cool-vis + creator, 0.577, a hair under the 0.577
median). More telling than the count: all 45 tag-pair bridges live in a
narrow band (0.556-0.631), every one of them roughly 2x the corpus
background, and bridge strength is nearly uncorrelated with endpoint
distance (fig 02). The registered fallback line — "an empty acquisition
list is itself the answer" — is the verdict: **this corpus has no
meaningfully weak bridges at the tag level.** The census said no desert
between cities; this says every pair of major cities already has a paved
crossing. Acquisition targeting, if it ever matters, must look below tag
granularity (note-level gap stretches), not at it.

## Figures

- `01-highway.png` — vocabulary handover + feature lanes for the
  registered highway
- `02-missing-bridges.png` — 45 bridges in a 0.07-wide band, the one
  starred crossing barely under the median

## Render

```bash
uv run --with matplotlib python scripts/query_spaces.py
```
