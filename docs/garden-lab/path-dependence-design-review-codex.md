```json
{
  "verdict": "run-with-changes",
  "findings": [
    {
      "id": "P1",
      "severity": "critical",
      "argument": "The proposed theta policy is underspecified in a way that changes the experiment. A growth trigger should divide attachments by the note count at the last derivation, not by the continually growing current size; otherwise theta=0.50 requires the cache to double before the ratio reaches 0.50 and, with a 50% base plus a strict 'exceeds' test, can become observationally identical to never. Scoring only at 10%-spaced checkpoints also misses the worst staleness immediately before a rebuild and can make a policy look perfect when it happens to rebuild just before 100%.",
      "required_change": "Define trigger debt as attached_since_rebuild / n_at_last_rebuild and fire on >= theta. Record metrics immediately before and after every rebuild as well as at fixed checkpoints; add a time-weighted mean/AUC across the replay and define max transient divergence over those event-level observations, not checkpoint samples alone. Unit-test exact trigger positions for every theta."
    },
    {
      "id": "P2",
      "severity": "critical",
      "argument": "Granularity is not matched by construction. The incremental tree is fit once at the 50% prefix, while each reference calls fit_nodes on a larger prefix; fit_nodes changes k_main at n//80 thresholds and changes sub-splitting when limbs cross 60 notes. For ai-building in particular, the 50% base and full prefix request different main-cluster counts. The resulting divergence mixes attachment path dependence with an explicit increase in model capacity.",
      "required_change": "Report two references: a production-fresh reference using fit_nodes exactly as shipped, and a diagnostic matched-capacity reference with k_main/sub-split policy frozen to the base tree. Use the production reference for the shipping frontier but use the matched-capacity arm to attribute divergence. Record every checkpoint's requested k_main, node count, depth profile, and threshold crossings; remove the claim that granularity is already matched."
    },
    {
      "id": "P3",
      "severity": "critical",
      "argument": "The design calls the date sort the real production arrival order, but the grove work already established that many notes are undated and some available dates represent content/upload time rather than ingest time. Sorting missing dates to the end fabricates a large terminal burst, while ties inherit an arbitrary corpus order. That path is useful as a date-ordered stress case but is not defensible as the primary production replay without an actual ingest sequence.",
      "required_change": "Use a persisted ingest/index order or snapshot history as the primary order if one exists. Otherwise rename the arm date-ordered, publish dated coverage and tie counts per bucket, randomize within equal-date groups, place undated notes through an explicitly reported sensitivity scheme rather than all at the end, and do not claim that this arm reproduces production arrival. Keep fully random permutations as sensitivity controls."
    },
    {
      "id": "P4",
      "severity": "major",
      "argument": "The proposed mass metric does not yet measure renderer-visible mass placement. anchor_nodes constructs overlap sets only from direct note memberships, so roots and internal limbs with all notes assigned to descendants are unmatched even though their mass controls rendered girth. Spearman on the surviving matches ignores unmatched mass, matching coverage, and error magnitude; it can equal 1.0 when every branch is badly mis-scaled but rank order is preserved.",
      "required_change": "Build descendant-note sets for every node and match all renderer-visible nodes, preserving ancestor consistency where possible. Report matched node count, matched descendant-mass coverage, unmatched mass, Spearman rank correlation, and a magnitude metric such as mass-share L1 error or weighted absolute percentage error. Use the magnitude/coverage pair, not Spearman alone, on the policy frontier."
    },
    {
      "id": "P5",
      "severity": "major",
      "argument": "LCA triplet agreement is appropriate in direction but can become selective and noisy on these shallow two-level trees. Many note triplets tie because notes share nodes or only coarse LCAs; skipping every tied triplet can leave a small, nonrepresentative usable subset. A single 2,000-triplet draw per checkpoint supplies neither coverage nor Monte Carlo uncertainty, and returning a numeric score when no usable triplets remain would be misleading.",
      "required_change": "Record attempted, usable, and tie-rejected triplets plus usable fraction at every checkpoint. Use multiple deterministic triplet seeds or a shared pre-generated triplet sample with a Monte Carlo interval, return null below a preregistered usable-count threshold, and include a fixed-mapping structural-null score as a calibration check on representative cells. Reuse identical sampled note triplets across theta policies for paired comparisons."
    },
    {
      "id": "P6",
      "severity": "major",
      "argument": "A single 50% initialization cannot support a general rebuild policy, because path dependence depends on how mature the tree was when last derived. It also omits the cheapest plausible mitigation: production centroids are frozen after derivation, so divergence may come from stale attachment targets rather than immutable topology. A rebuild-only frontier could recommend expensive churn when online centroid maintenance would recover much of the signal.",
      "required_change": "Add temporal-order base-fraction sensitivity at approximately 25%, 50%, and 75%, raising the smallest base to the 30-note clustering floor where necessary; the random-order factorial can remain at 50%. Add a no-topology-rebuild comparator that updates terminal-node and ancestor centroids online from maintained sums/counts, and report attachment target depth/root rate. This separates stale-centroid error from no-split topology error and exposes a cheaper shipping option."
    },
    {
      "id": "P7",
      "severity": "major",
      "argument": "Rebuild count is not a comparable cost measure across buckets: an average-linkage rebuild on 2,065 notes has quadratic pairwise work and is vastly more expensive than one on 86 notes. The current factorial also recomputes the same fresh checkpoint references independently for every theta, wasting most of the overnight budget and increasing the temptation to over-parallelize memory-heavy linkage fits.",
      "required_change": "Report measured wall time, peak memory if available, and a deterministic work proxy such as sum of n_rebuild^2 in addition to rebuild count. Freeze one versioned input artifact containing vectors, note keys, dates/order metadata, embedding/config hashes, and corpus hash; precompute each bucket/order/prefix fresh reference once and reuse it across theta cells. Require a complete expected-cell manifest, atomic unique output paths, deterministic cell-derived seeds, schema/hash validation at merge, and bounded concurrency."
    }
  ],
  "answers": {
    "q1": "The battery covers the right three constructs only after P2, P4, and P5: flat assignment, ordinal ancestry, and renderer-visible mass. Do not add an unvalidated image or E7-derived legibility score as a decision gate; E7 established that full-tree geometry can carry identity, not a numerical threshold for acceptable cache drift. An optional renderer-facing diagnostic using common geometry seeds and normalized silhouette or branch-feature deltas is reasonable, but the decision-grade additions are mass-error magnitude and coverage, triplet usable coverage/uncertainty, node-count/depth drift, attachment target depth, and time-weighted/worst pre-rebuild divergence.",
    "q2": "Use {0.10, 0.25, 0.50, 1.00, never} with the denominator fixed to n_at_last_rebuild and >= semantics; theta=1.00 supplies the meaningful 'double before rebuilding' point that the present formulation accidentally assigns to 0.50. If small-bucket churn is operationally undesirable, simulate a hybrid trigger max(theta * n_at_last_rebuild, absolute_floor) with the absolute floor stated explicitly. Choose from the temporal/production frontier, using random orders and base-fraction arms as robustness checks rather than averaging them into the primary decision.",
    "q3": "Parallel per-cell execution is acceptable after the corpus is frozen to a read-only hashed input artifact and fresh references are factored out for reuse. Give every cell a unique atomic output path and deterministic seed derived from its full parameter tuple, cap concurrency to avoid simultaneous O(n^2) linkage memory pressure, and make the merger reject missing, duplicate, schema-mismatched, or input-hash-mismatched cells. Parallel agents should orchestrate independent cells only; they should not each resolve a live Chroma corpus or write the merged artifact."
  }
}
```
