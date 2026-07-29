# Codex external review response: overnight path-dependence study

```json
{
  "verdict": {
    "results_valid": "with-corrections",
    "theta_025_recommendation": "ship-with-conditions",
    "gate72_swap": "hold",
    "summary": "The 144 artifacts are complete and internally consistent, the headline never-rebuild failures recompute, and theta=0.25 is a defensible provisional containment policy rather than a uniquely measured optimum. Several attribution claims overreach because the requested time-weighted AUC and fully frozen-capacity comparator were not implemented, while the centroid-maintain comparator is initialized incorrectly. Hold the gate stamp until its metric is aligned or explicitly labeled and its single temporal estimate is Monte Carlo-repeated with coverage statistics."
  },
  "findings": [
    {
      "id": "K1",
      "severity": "major",
      "target": "C5",
      "argument": "The reported AUC is not the time-weighted AUC required by P1; it is an unweighted mean over three or five fixed checkpoints, with null triplets silently removed. That leaves the policy ranking sensitive to checkpoint/trigger phase, exactly the artifact the design correction was meant to eliminate. Direct recomputation also shows theta=0.1 has the most best-or-tied arms more often than theta=0.25 for both triplet AUC (13 versus 12) and assignment AUC (14 versus 9); theta=0.25 becomes the knee only after assigning a cost to 7 rebuilds versus 3, while the report says compute cost is negligible and does not measure churn.",
      "evidence_or_repro": "scripts/grove_lab/replay.py:360-370 computes np.mean over available checkpoints; path-dependence-report.md sections 2 and 6 acknowledge checkpoint luck and null dropping. Re-aggregate all replay-cells by taking the maximum auc.triplet and auc.assignment_ari among rebuild policies per bucket/order/base arm.",
      "required_change": "Rephrase C5 as an operationally preferred provisional tradeoff, not a data-identified optimum. Before claiming a frontier knee, score on a denser common time grid or compute a preregistered time-weighted integral that includes null/low-coverage handling, and quantify the continuity/churn cost used to prefer 3 rebuilds over 7. Shipping theta=0.25 is still a conservative improvement over never, but its constant should remain configurable and telemetry-backed."
    },
    {
      "id": "K2",
      "severity": "major",
      "target": "C4",
      "argument": "The centroid-maintain comparator is not correctly initialized for internal nodes. Nodes without direct note membership, including roots and many internal limbs, receive the global mean as one pseudo-observation (_sum=centroid, _count=1), then are updated only with newly attached notes; this is not the centroid of their existing descendant mass. Since attachment searches all nodes, the malformed internal centroids can change targets and make maintenance look harmful. The categorical dominance statement is also numerically false: ai-building random seed 102 has centroid-maintain assignment AUC 0.586 versus theta=0.25 at 0.580.",
      "evidence_or_repro": "scripts/grove_lab/replay.py:104-112 and 238-254; compare docs/grove-lab/replay-cells/ai-building-102-0.5-centroid-maintain-never.json with ai-building-102-0.5-rebuild-0.25.json. Across 24 centroid-maintain/never arms, centroid maintenance is worse in 19 for assignment AUC and final ARI, but only 12 for triplet AUC, final triplet, and final mass L1; '~3/4' is metric-dependent.",
      "required_change": "Initialize every node's sum/count from all descendant members, rerun centroid-maintain, and separately test terminal-only attachment because fresh fit_nodes assigns notes only to terminal membership nodes while production attach currently considers roots/internal nodes. Retract 'dominated in every cell' and report worse/better counts separately per metric. This does not block shipping periodic rebuilds, but it invalidates the claim that correct online centroid maintenance has been rejected."
    },
    {
      "id": "K3",
      "severity": "major",
      "target": "C3",
      "argument": "The matched-capacity reference freezes only k_main, not the sub-split thresholds or k_sub requested by P2. This matters empirically: visual-craft's incremental base-0.5 tree remains at 4 nodes while both production and so-called matched-capacity references grow to 6 nodes at later prefixes even though k_main stays 3. The report's statement that ai-building is the only capacity-starved bucket is therefore false; visual-craft also gains sub-branch capacity. Epicmap's equal 15-node counts do support the narrower conclusion that its observed divergence is not explained by node-count growth.",
      "evidence_or_repro": "scripts/grove_lab/replay.py:61-100 accepts only a frozen k_main and recomputes sub-splits at lines 82-95. In visual-craft-date-0.5-rebuild-never.json, incremental_nodes stays 4 while production and matched_capacity ref_nodes become 6 at n=68, 77, and 86.",
      "required_change": "Correct the report to identify visual-craft sub-split capacity starvation. Rename the existing arm 'matched-k-main' or implement a genuinely frozen topology-capacity policy covering sub-split eligibility and k_sub before using it for causal attribution. Keep the epicmap no-node-count-growth observation, but describe 'genuine path dependence' as divergence not attributable to measured capacity counts rather than a fully isolated cause."
    },
    {
      "id": "K4",
      "severity": "major",
      "target": "C1",
      "argument": "C1 is both factually too narrow and calibrated against a non-equivalent floor. At base 0.25 the date-arm never policy finishes below the quoted floor in all three buckets, not only epicmap: 0.493/0.596, 0.680/0.752, and 0.701/0.738. At base 0.5 visual-craft date is also slightly below (0.732 versus 0.738). More fundamentally, shootout-v3 floors use full-linkage cophenetic triplets across disjoint halves with nearest-neighbor leaf mapping, whereas replay uses truncated fit_nodes LCA triplets over the same prefix notes; equality of their numeric scores does not establish statistical indistinguishability.",
      "evidence_or_repro": "path-dependence-report.md sections 3-4 and the corresponding *-date-0.25-rebuild-never.json cells; compare scripts/grove_lab/shootout.py:92-111 with scripts/grove_lab/replay.py:119-169 and 258-276.",
      "required_change": "Replace the floor verdict with raw replay agreement and usable-triplet coverage. If a stability threshold is wanted, generate a replay-specific refit/null distribution using the identical truncated LCA metric, same-note comparison contract, prefix sizes, and sampling rules. Until then say ordinal hierarchy degrades less than assignment/mass at mature bases, not that corruption is below intrinsic noise."
    },
    {
      "id": "K5",
      "severity": "major",
      "target": "W4",
      "argument": "Mass-share L1 is a matched-node lower bound, not total renderer-visible mass error, because unmatched nodes contribute zero rather than an explicit penalty. The epicmap never headline has six unmatched nodes on each side and 0.902 coverage; changing the Jaccard cutoff can alter both the matched set and L1. The result still demonstrates substantial drift, but 0.685 should not be read as a complete distance between rendered girth distributions.",
      "evidence_or_repro": "scripts/grove_lab/replay.py:200-231 sums L1 only over matched pairs. epicmap-date-0.5-rebuild-never.json final mass reports matched_nodes=9, unmatched_a=6, unmatched_b=6, coverage=0.902, mass_l1=0.685.",
      "required_change": "Label mass_l1 as matched-mass L1 throughout, keep coverage adjacent to every headline, and add an unmatched-mass penalty or report lower/upper bounds. Sweep the Jaccard cutoff on representative cells. This correction strengthens rather than reverses C2: the current 0.685 is already large despite omitting unmatched branches."
    },
    {
      "id": "K6",
      "severity": "major",
      "target": "W6",
      "argument": "The recommended 15-note absolute floor was not part of any replay cell, so the policy proposed for shipping is not the measured theta=0.25 policy. The difference is largest for young and small buckets—the exact regime where base-0.25 transients were worst and where the floor is intended to act. It does not affect the three current large snapshots until their 25% debt exceeds 15, but it controls sapling promotion and future bucket behavior.",
      "evidence_or_repro": "All replay-cells encode theta and policy only; scripts/grove_lab/replay.py:322-324 has no absolute floor. morning-decisions.md item (a) adds 15 notes after the experiment.",
      "required_change": "For the morning ship, either implement pure theta=0.25 for already-clustered snapshots and leave saplings unchanged, or run the inexpensive hybrid max(0.25*n_at_last_rebuild, 15) replay before enabling it globally. Stamp the policy parameters in snapshots and keep the floor configurable rather than presenting 15 as measured."
    },
    {
      "id": "K7",
      "severity": "major",
      "target": "new",
      "argument": "gate72.json is not yet decision-grade as a snapshot stability stamp. For each temporal bucket it contains one deterministic half split and one Monte Carlo triplet draw despite the top-level seeds=10, reports no used/noninjective/tie counts, and evaluates the full scipy linkage dendrogram rather than the truncated fit_nodes topology actually stored and rendered. It is a better construct than flat centroid-transfer ARI, but the values 0.478/0.616/0.673 can be misread as stability of the shipped snapshot geometry.",
      "evidence_or_repro": "scripts/grove_lab/gate72.py:37 declares SEEDS=10, but lines 51-69 create one temporal half pair and one RNG call; lines 64-69 fit full linkage and discard triplet return_stats. gate72.json records halves=1 for all three large buckets.",
      "required_change": "Hold the stamp long enough to repeat triplet sampling over at least 10 deterministic seeds on the fixed temporal halves, record mean/range plus collision/used/tie statistics, and either evaluate the actual fit_nodes node tree or name the field explicitly full_linkage_triplet so it cannot be mistaken for rendered-snapshot stability. Then replace ARI; the direction of the gate swap remains endorsed."
    }
  ],
  "answers": {
    "blocking_for_morning_ship": [
      "K6",
      "K7"
    ]
  }
}
```
