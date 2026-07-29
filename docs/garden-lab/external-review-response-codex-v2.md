# Codex external review response: grove E2 v2

```json
{
  "verdict": {
    "v2_corrections": "sound",
    "triplet_metric": "trustworthy-with-fixes",
    "e7_protocol": "run-with-changes",
    "summary": "The v2 corrections appropriately retract the method shootout, causal drift claim, and epicmap flat-structure claim. Triplet agreement is better aligned with a tree product than flat ARI, but the present implementation validates only directional ordinal relationships and cannot yet justify literal dendrogram distances or replace the production gate. E7 is salvageable before exposure, but its discrimination task, shuffled null, and binomial analysis must change."
  },
  "findings": [
    {
      "id": "G1",
      "severity": "critical",
      "target": "E7",
      "argument": "The discrimination task has no coherent same-topic/different-topic ground truth. Both (true_i, shuffled_i) and (true_i, true_i rerendered) are generated from bucket i, so both are the same topic; treating a shuffled realization as a different topic silently changes the question from topic identity to visual-topology similarity. A subject can also solve true-versus-rerendered trials by recognizing repeated structure without reading topic identity, which would validate perceptual invariance rather than semantic legibility.",
      "evidence_or_repro": "external-review-handoff-v2.md section 4, Tasks (b): enumerate the bucket label attached to each member of both proposed pair classes; both labels are i.",
      "required_change": "Split the construct into two explicitly descriptive tasks. For semantic readback, present a bucket name and a forced choice between its true tree and a constrained shuffled control, with left/right randomized. For topology perception, use an anchor-and-two-candidate match task where one candidate is the same topology rerendered and the other is its constrained shuffle; do not call that task topic discrimination or use it as the legibility gate.",
      "confidence": 0.99
    },
    {
      "id": "G2",
      "severity": "major",
      "target": "N1",
      "argument": "The triplet score records only which pair is cophenetically closest. It is invariant to monotone transformations and discards the magnitude of all cophenetic distances, so values of 0.6-0.78 can support reproducible ordinal branching relationships but cannot justify literal relative distances, persistence magnitudes, or placement geometry. N1 overclaims what the metric measures.",
      "evidence_or_repro": "scripts/grove_lab/shootout.py:59-82 reduces each tree's three cophenetic distances to argmin(db) and argmin(da); construct two dendrogram distance matrices with the same ordering but arbitrarily different distance ratios and the score remains 1.0.",
      "required_change": "Narrow N1 to reproducible coarse ordinal hierarchy. Before claiming relative-distance fidelity, add a separately reported metric such as rank correlation of matched cophenetic distances, distortion after monotone calibration, or agreement in persistence ordering. Do not map the current triplet value directly to geometric distance confidence.",
      "confidence": 0.99
    },
    {
      "id": "G3",
      "severity": "major",
      "target": "T1",
      "argument": "The current triplet comparison is directional and collision-prone. Every B leaf maps to one nearest A leaf, multiple B leaves may collapse to the same A representative, and the reverse A-to-B comparison is never computed. Collapsed pairs produce zero A-side distances and can win argmin by construction; ties in da are not skipped, so np.argmin resolves them by fixed pair order. The resulting statistic mixes hierarchical agreement with nearest-neighbor coverage and pair-order tie behavior.",
      "evidence_or_repro": "scripts/grove_lab/shootout.py:68 maps only vb to va; lines 73-80 skip ties only when len(set(db)) < 2, not when da ties. Run a synthetic case where reps[i] == reps[j] for many sampled pairs and compare scores before and after excluding non-injective triplets.",
      "required_change": "Report both A-to-B and B-to-A scores and their mean; reject triplets whose mapped representatives are not all distinct; skip ambiguous closest-pair ties on either side; report mapping collision rate and usable-triplet count per bucket. Prefer mutual-nearest-neighbor anchors or matched local prototypes if enough anchors remain, and add synthetic tests covering collisions and ties.",
      "confidence": 0.98
    },
    {
      "id": "G4",
      "severity": "major",
      "target": "E7",
      "argument": "Uniform random parent assignment is an inadequately matched null. It will generally alter depth, degree, balance, mass-by-depth, persistence-by-depth, and silhouette roughness, allowing true trees to be selected because they look more orderly or biologically plausible rather than because topic-specific topology is legible. Matching only the marginal mass and persistence multisets does not preserve their joint placement in the hierarchy.",
      "evidence_or_repro": "external-review-handoff-v2.md section 4, Stimuli. For generated controls, compare distributions of maximum depth, mean leaf depth, node degree, subtree mass by depth, persistence by depth, and rendered bounding-box/silhouette statistics against the source tree.",
      "required_change": "Generate controls with constrained subtree reattachments or degree-preserving edge swaps that retain node count, root degree, depth histogram, child-count sequence, and mass/persistence strata by depth while breaking which semantic subtrees are adjacent. Pre-generate several candidates and accept only controls within preregistered structural tolerances; do not hand-select visually convincing shuffles.",
      "confidence": 0.96
    },
    {
      "id": "G5",
      "severity": "major",
      "target": "T2",
      "argument": "The 0.33 shuffled baseline is a useful pipeline sanity check but not a structural null: permuting vb breaks the embedding-to-leaf correspondence used for cross-half mapping while leaving Zb fixed. Beating it shows that some shared embedding neighborhood signal survives, not that the fitted hierarchy contributes information beyond geometry or near-duplicate content. A label permutation cannot alter an unlabeled linkage tree, and arbitrary distance permutation may violate metric and dendrogram constraints, so the proposed sharper nulls need careful definition.",
      "evidence_or_repro": "scripts/grove_lab/shootout.py:217 passes vb[rng.permutation(len(vb))] while retaining the original Zb. Compare the observed score with (1) the same cross-half mapping evaluated on structurally randomized dendrograms preserving leaf depths/degrees and (2) linkage trees fit after within-half feature rotations or neighbor-preserving controls chosen to isolate the claimed component.",
      "required_change": "Retain the mapping-shuffle baseline but label it as a correspondence-null. Add a tree-structure null that holds the cross-half leaf mapping fixed and randomizes dendrogram structure under preserved size/depth/degree constraints. Add a content-similarity exclusion or deduplication sensitivity analysis as specified in T3.",
      "confidence": 0.94
    },
    {
      "id": "G6",
      "severity": "major",
      "target": "T5",
      "argument": "The reported brackets are percentile ranges over only 10 split scores, not calibrated 95% confidence intervals, and 2,000 triplets within a split are highly dependent because they repeatedly reuse the same leaves and fitted trees. Treating 12 repeated E7 responses from one subject and six underlying tree classes as independent Bernoulli trials creates the same pseudo-replication problem. The proposed p<.05 rule is also brittle: in 12 fair binary trials it requires at least 10 correct, so one or two learned or ambiguous responses determine the verdict.",
      "evidence_or_repro": "scripts/grove_lab/shootout.py:50-56 uses empirical 2.5/97.5 percentiles and lines 209-220 supply 10 split values; external-review-handoff-v2.md section 4 proposes exact binomial inference over repeated rerenders of only three buckets. Compute P(X>=10 | n=12, p=.5)=0.0193 and P(X>=9)=0.0730.",
      "required_change": "Call the triplet brackets seed/split ranges, increase independent split repetitions, and use a hierarchical or split-level bootstrap rather than triplets as independent units. For E7, preregister the result as a single-subject case study with trial-level outcomes and no population-generalizing p-value; define success separately per task and report learning/order effects. If a binary threshold is retained, preregister the exact required score and an inconclusive region before exposure.",
      "confidence": 0.97
    },
    {
      "id": "G7",
      "severity": "major",
      "target": "N3",
      "argument": "Agglomerative linkage is a reasonable provisional engineering choice because it is deterministic and yields a complete dendrogram, but the current evidence does not establish that HDBSCAN is unusable for a stable cache. Bimodal flat-cut transfer ARI may reflect unstable cluster extraction, noise labeling, or parameter sensitivity rather than unstable coarse condensed-tree geometry. HDBSCAN has not been evaluated on the construct now declared primary.",
      "evidence_or_repro": "external-review-handoff-v2.md N3 and T4; shootout-v2 evaluates HDBSCAN only through flat labels returned by fit_hdb in scripts/grove_lab/shootout.py:102-107, while triplet_agreement is run only on average-linkage at lines 203-220.",
      "required_change": "Keep agglo as the provisional implementation source, but phrase N3 as a product decision based on determinism and complete-tree availability. Do not claim comparative cache unsuitability until condensed-tree geometry receives the corrected hierarchy gate across parameter sweeps and seeds.",
      "confidence": 0.94
    },
    {
      "id": "G8",
      "severity": "minor",
      "target": "N2",
      "argument": "N2 is mostly supported after narrowing C6, but 'branch geometry' remains ambiguous. The score can justify rendering a coarse unnamed ordinal hierarchy; it does not independently validate exact branch lengths, golden-angle placement, mass-to-girth mapping, or stable branch identities. The interface and report should not let geometry imply more precision than was tested.",
      "evidence_or_repro": "Compare N2 with scripts/grove_lab/shootout.py:59-82 and web/src/lib/grove/datatree.ts mappings: only closest-pair order is measured, while the renderer exposes several continuous and aesthetic variables.",
      "required_change": "State that epicmap has reproducible coarse ordinal hierarchical relations under the tested linkage procedure. Continue suppressing names and semantic identities, and describe continuous branch lengths and layout as visual encodings pending separate validation.",
      "confidence": 0.95
    }
  ],
  "e7_protocol_edits": [
    {
      "section": "stimuli",
      "change": "Replace uniform-parent shuffles with automatically generated constrained controls preserving depth histogram, degree sequence or child-count profile, root degree, node count, and mass/persistence strata by depth. Normalize presentation scale across bucket choices for semantic trials, or run a preregistered scale-present and scale-absent block if product-scale contribution is itself of interest.",
      "rationale": "The control must remove topic-specific organization without introducing obvious unnaturalness or allowing bucket size to answer the question. A separate product block can later measure whether hue and scale help the shipped experience."
    },
    {
      "section": "randomization",
      "change": "Pre-generate and hash the complete manifest, randomize left/right and order, balance bucket and condition across early and late trials, and record camera/render seeds. Use no feedback and include a short practice using synthetic trees unrelated to the three buckets.",
      "rationale": "This limits learning, side bias, accidental seed leakage, and post hoc stimulus selection while preserving the only naive exposure."
    },
    {
      "section": "tasks",
      "change": "Use two named tasks: (1) semantic readback: show one bucket name and ask which of two structurally matched trees is its true tree; the foil is a constrained shuffle and left/right is randomized; (2) topology invariance: show an anchor and ask which of two candidates shares its topology, with one rerender and one constrained shuffle. Keep 3-AFC isolated-tree identification exploratory, collect confidence after every answer, and never label task 2 as same-topic/different-topic discrimination.",
      "rationale": "Task 1 tests whether data-derived organization carries readable topic identity; task 2 tests whether the rendering preserves perceptible topology. The draft conflates these constructs and assigns a false different-topic label to a same-bucket shuffle."
    },
    {
      "section": "analysis",
      "change": "Drop the single p<.05 legibility gate. Preregister exact scoring for each task, trial exclusions, an inconclusive outcome, per-bucket results, confidence, response time, and early-versus-late performance. Treat the run as a descriptive single-owner case study; report exact binomial tail probabilities only as conditional summaries, not independent-subject evidence.",
      "rationale": "Repeated views of three underlying buckets are not twelve independent replications of topic legibility, and the current 10-of-12 threshold is too discontinuous for an irreversible one-subject experiment."
    },
    {
      "section": "implementation",
      "change": "Make the readback route consume an immutable, versioned manifest containing stimulus hashes, control-generation constraints, presentation order, left/right truth, camera seeds, and analysis version. Append responses without exposing correctness; preserve the raw log and do not overwrite it on rerun.",
      "rationale": "The irreversible exposure needs an auditable distinction between preregistered stimuli, raw observations, and later interpretation."
    }
  ],
  "work_ranking": [
    "B — Correct and freeze E7 first because the only naive subject can be exposed once; do not run until G1, G4, and G6 are resolved in the manifest and analysis plan.",
    "E — Give HDBSCAN the corrected symmetric hierarchy gate so the retained topology source is a fair product choice rather than a conclusion inherited from the retracted flat shootout.",
    "C — Publish bucket overlap/coherence and the dedupe reconciliation before interpreting either metric or E7; first-match bucket contamination and near-copies can affect both.",
    "D — Quantify arrival-order path dependence before treating cached continuity as evidence-bearing structure or designing an automatic split/rebuild policy.",
    "A — Swap and restamp the production gate only after G2, G3, G5, and G6 are fixed and thresholds are calibrated against structural nulls; the current metric is promising but not production-ready.",
    "F — Run the hyperbolic challenger only if the corrected hierarchy comparison, cache replay, or E7 weakens agglo; it remains lower-value complexity today."
  ],
  "endorsements": [
    "The v2 report correctly retracts the claim that agglo decisively beats HDBSCAN: with 20 paired seeds and both centroid and kNN transfer, the intervals crossing zero directly invalidate the earlier winner language.",
    "The epicmap conclusion is now appropriately narrowed: the evidence rejects reproducible flat partitions at k=3-12 but no longer denies all structure.",
    "AI-building should be described as temporally non-stationary rather than semantically drifting; the measured source-mixture shift is a concrete unresolved confound.",
    "A hierarchy-aware gate is the correct construct direction for a tree product, and closest-pair triplets are an interpretable component of that gate once mapping collisions, directionality, ties, and null calibration are repaired.",
    "Agglomerative average-linkage remains a defensible provisional topology source because determinism and a complete dendrogram are real product requirements, even though comparative scientific superiority is not established.",
    "E7's isolation, neutral tint, randomized view, hidden labels/exemplars, and pre-exposure manifest are strong controls worth preserving; the protocol needs sharpening rather than wholesale redesign."
  ]
}
```
