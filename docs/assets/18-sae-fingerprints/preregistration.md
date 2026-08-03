# Pre-registration — sections 18 (SAE fingerprints), 19 (rank metrics), 20 (query spaces)

Committed before any measurement in these sections runs. Each experiment
states its question, a falsifiable prediction, the control it is judged
against, and the kill criterion that stops the line. Results that contradict
a prediction are reported as such; predictions are never edited after the
fact. Landscape facts and API details: `landscape.md` (verified 2026-08-02).

## Section 18 — SAE feature fingerprints

SAE: `gemma-scope-2b-pt-res`, layer 20, width 16k, average L0 71 (the
Neuronpedia-named configuration). Texts: thesis + summary per note, the same
content the Qwen3 embeddings encode. Both mean- and max-pooled fingerprints
kept throughout (prior art max-pools; unsettled for 100-300-token notes).

### 18.0 — API smoke test

Question: do the endpoint shapes in landscape.md hold, and do the named
features for one real technical note pass a sniff test?
Prediction: at least 6 of the top 10 features for a known coding-topic note
have names recognizably related to its content (topic, register, or
programming domain) rather than pure formatting/token-level features.
Control: none — this is an instrument check.
Kill: fewer than 3 of 10 recognizable — stop, revisit layer/width before
building anything.

### 18.1 — local rig cross-validation

Question: does the local CPU pipeline reproduce Neuronpedia's reference
inference?
Prediction: on 5 notes, local top-10 feature sets overlap the API's top-10
by at least 7/10 on average (ordering may differ; activation values within
10% on shared features).
Control: the API is the reference implementation.
Kill: overlap below 5/10 on any note — hook-name or numerics bug; do not
run the batch on an unvalidated rig.

### 18.2 — full batch

Instrument step, no hypothesis. Recorded acceptance check: mean per-note L0
within a factor of 2 of the advertised average 71; fewer than 1% of notes
with zero active features. Artifacts: fp16 npz (both poolings), manifest,
L0 + feature-frequency figures.

### 18.3 — name the cone

Question: is the shared offset every note carries (‖mean‖ = 0.51 in Qwen3
space) readable as named features?
Prediction: at least 5 features are active in >90% of notes, and their
names describe register/domain (technical English, explanatory prose,
AI/programming) rather than looking arbitrary.
Control: document frequencies against a permutation null (activations
shuffled across notes per feature) to separate "always-on" from chance.
Secondary, exploratory (not confirmatory): projection of always-on
features' decoder directions onto Gemma's own residual mean — the Qwen3
cone direction lives in a different space and cannot be compared directly;
any cross-space claim requires text-level evidence, not vector algebra.
Kill: no feature exceeds 70% document frequency — conclusion becomes "the
shared component is not in the SAE dictionary", which is itself reportable.

### 18.4 — tag regions as feature sets

Question: do interest_tags correspond to coherent differential feature sets?
Prediction: for at least 7 of the 10 largest tags, the top-15 differential
features (tag-mean fingerprint minus corpus mean) are topically coherent
with the tag name, judged per tag and recorded before seeing the other
tags' results. Quantitative companion: pairwise tag feature-set Jaccard
correlates with Qwen3 centroid cosine at r >= 0.4.
Control: tag labels shuffled across notes; differential features above the
real threshold should nearly vanish.
Kill: fewer than 4 of 10 tags coherent — feature diffing does not carve
this corpus; stop before building anything on it.

### 18.5 — roads as feature diffs

Question: does a slerp road read as monotone feature turnover?
Prediction: along the E6 road (interview -> instagram heatmap), the share
of A-side features among each stop's retrieved notes decreases
monotonically in t (Spearman rho <= -0.8 across stops), and the
fading-out / persistent / fading-in sets are all non-empty with readable
names.
Control: a random re-ordering of the same stops must not show monotone
turnover.
Kill: no monotone structure — feature space does not track the walk;
roads keep LLM narration and drop the feature readout, reported honestly.
Judgment call recorded up front: whether the set-diff readout beats the
existing Haiku narration is subjective; both are shown side by side and
the verdict is argued, not scored.

### 18.4b — continuous cross-space agreement (registered 2026-08-03, after
### 18.4's quantized companion failed at r = 0.391)

Question: was the 18.4 companion failure the quantization or the absence of
a relationship? Replace fifteenths-quantized Jaccard with a continuous
measure: per tag, the full 16384-dim differential-z vector from 18.4; per
tag pair, the cosine between those z-vectors (SAE side) against the Qwen
centroid cosine, over the same 45 pairs.
Prediction: r >= 0.4 — same threshold as the failed companion, kept
deliberately: if quantization was the problem, removing it should clear
the same bar, not a lowered one.
Control: z-vectors recomputed under shuffled tags give r near 0.
Kill: none; either answer resolves the question. Declared context: the
18.4 point estimates were already seen when this was registered — the
z-vectors themselves are reused, only the pair-similarity measure is new.

## Section 19 — rank metrics (Phase A, offline; Phase B only through the gate)

Metrics: cosine, cosine-centred, L1, Spearman (rank-transform then cosine),
Spearman-centred, CSLS(k=10). All on the fresh snapshot, read-only.

### 19.1 — tag-match@10

Prediction (from arXiv 2606.29571 given ‖mean‖ = 0.51): Spearman and L1
beat raw cosine on tag-match@10 by >= 2 points absolute; after centring the
rank-vs-cosine gap shrinks below 1 point.
Control: permuted-tag baseline sets the floor.
Kill: none (any outcome is informative), but Phase B is only earned by a
win >= 2 points from some non-cosine metric.

### 19.2 — hub flattening

Prediction: CSLS(k=10) cuts the census top-10 answerer share (12%) by at
least a third while path min-support distribution shifts by less than 0.01
at the median.
Control: the existing census under cosine is the baseline.

### 19.3 — duplicate detection

Prediction: the known duplicate pair (rndyrbrts DWpSK4uDhIO twice) ranks
strictly higher relative to ordinary near-neighbors under CSLS than under
cosine.

### 19.4 — Phase B (gated)

Only if 19.1 shows the win: metric behind a flag in store.py, judged by
`uv run ytk eval` against the frozen baseline. The gate's verdict is final;
no re-stamping.

## Section 20 — query spaces (designed in detail only after 18/19 report)

Pre-registered at mode level now, deliberately not in detail — detailed
designs would assume 18/19 conclusions this plan exists to earn:
barycentric 3-note blends, local-PCA region windows, extrapolation past an
endpoint, tag-centroid roads, low-support gap hunting. Each will get its
own prediction/control/kill block appended here before it runs, under
whichever metric section 19 selects and whichever readout (feature diff vs
narration) section 18.5 selects. The first artifact of section 20 is the
road between the two strongest coherent interests, so the machinery is
demonstrated on interests that matter, not a deliberately weird pair.

## Section 20 — query spaces (detailed registration 2026-08-03, after 18/19)

Inherited instrument rules: cosine retrieval (19.1's verdict), content-identity
dedup, mass presence, sum pooling, auto-names as probed hypotheses.

### 20.1 — the highway: tag-centroid road between the two strongest interests

Endpoint rule, fixed before looking: A = the most coherent tag by fresh z
(17-corpus-growth E3); B = the next most coherent tag whose Qwen centroid
cosine with A is below the median of the 45 large-tag pairs (guaranteeing a
genuinely distinct region). Nine slerp stops between unit centroids, top-3
notes per stop, feature lanes from the tags' mean fingerprints (top-256
vocabularies).
Predictions: (a) support >= corpus background at every stop; (b) A-side
feature share monotone in t, Spearman rho <= -0.8; (c) at least one stop's
top note carries neither endpoint tag — a genuine bridge note.
Control: shuffled stop order for (b), as in 18.5.
Kill: none — each sub-verdict recorded separately.

### 20.2 — barycentric blends (registered now, runs later)

Spherical weighted mean of 3 notes vs the three pairwise midpoints.
Prediction: in >= 3 of 10 seeded coherent triples, the barycenter's top
retrieved note differs from all three midpoints' top notes — the mode
expresses queries pairwise roads cannot. Control: degenerate triples
(note plus its two nearest neighbors) should show no such novelty.

### 20.3 — extrapolation past an endpoint (registered now, runs later)

Walk t in (1, 1.75] beyond B on the A->B arc ("more of B, away from A").
Prediction: support decays with t but stays above corpus background
through t = 1.5 — the cone keeps even extrapolations inhabited.
Verdict decides whether "more of this, less of that" is a usable query.

### 20.4 — gap hunting: the missing-bridges list

All 161k note pairs' midpoint support (t = 0.5, endpoints excluded from
retrieval). Aggregate to the 45 large-tag pairs: mean midpoint support
per tag pair, against endpoint centroid cosine.
Prediction: at least 2 of the 45 pairs combine two individually coherent
tags (fresh z > 2) with mean midpoint support below the all-pairs median
— genuinely weak bridges between real interests, i.e. named acquisition
targets for the feed. Control: the relationship between endpoint cosine
and midpoint support is reported alongside, so "weak bridge" is never
just "distant endpoints" restated.
Kill: none — an empty acquisition list is itself the answer.

## Standing rules

- Frozen artifacts are never overwritten; every results.json stamps seed
  and commit.
- A failed prediction is a result, published with the same prominence as a
  confirmation.
- Anything retrieval-behavior-changing reaches production only through the
  retrieval eval gate.
