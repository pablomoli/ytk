# Codex external review response v6 (verbatim, pasted from the tmux session)

Verdict: do NOT ship decisions (a) or (b) yet. Central failure: version
skew — the K2 fix changed a shared engine helper, only selected cells were
rerun, and new-engine cells were compared against old-engine cells.
Sixteen findings; the meta-finding: "review compliance is being treated as
experimental validity."

Key items (full text preserved in the session log):
1. Mixed replay engines: descendant centroids now initialize EVERY policy
   in replay.py, but only cm + hybrid cells were rerun; hybrid cells also
   do not simulate production (dendro.py keeps global-mean fallback).
   Fix: parameterize centroid semantics, rerun the whole comparable grid
   under one engine, stamp artifacts with schema + git commit.
2. Automatic theta rebuild is NOT a small mechanical change: persistent
   debt state, migration, atomicity, failure/concurrency behavior, tests.
3. Branch-length (persistence) staleness was never measured - one of the
   two principal continuous visual encodings.
4. fit_nodes_triplet lacks its own structural null (the reported null is
   full-linkage only).
5. Ten-seed ranges are triplet-sampling min/max on one fixed split, not
   stability uncertainty; report dated-note counts.
6. Gate integration needs schema versioning, migration, frontend/test
   changes, import restructuring.
7. Decision-doc hybrid numbers were copy-forwarded from pure-theta cells
   (real: 0.927/0.972/0.916; visual-craft hybrid = 2 rebuilds). CONFIRMED
   against artifacts.
8. Continuity cost is asserted AND current anchoring cannot support it:
   anchor_nodes matches direct members only, so internal nodes/root are
   never anchored.
9. Terminal-only attachment is the cheaper, better-motivated comparator
   (production attach can file notes at internal nodes/root - fresh fits
   never do); test it before split-on-mass.
10. Tiny-bucket within-similarity is biased (centroid contains the point);
    use leave-one-out.
11. "mind-systems is a centroid magnet" is suggestive, not established.
12. Dedupe title-only collisions unaudited.
13. 41% unmatched is not automatically a defect; characterize it first.
14. "Measurement is done" overstates E7 (one owner, three primaries, one
    renderer; visual-craft payload no-read; topology invariance 7/9).
15. Ingest-time capture is not a one-liner (consistency, immutability,
    migration, timezones).
16. Decoration is unblocked as PRODUCT work because the readback was
    encouraging - not because the representation is scientifically closed.

Recommended: hold (a) and (b); treat bucket-quality as exploratory;
capture ingest timestamps next; terminal-only attach before split-on-mass;
shaders may proceed independently.
