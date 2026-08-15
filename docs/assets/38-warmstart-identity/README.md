# 38 — The warm-start trade

The #83 identity layer (branch `feat/83-theme-identity`) gave every profile
theme a stable id by matching memberships across snapshots, and its threshold
sweep ended on an honest ceiling: with optimal thresholds, quiet daily
transitions still emit 5-7 lifecycle events, and the sweep showed the churn
comes from the KMeans refit itself — post-fit matching can only relabel it.
The plan's warm-start/PCM item had been demoted to "experiment, if the ceiling
ever matters". This section runs that experiment.

**Question:** does seeding each day's KMeans with the previous day's fitted
centroids reduce identity churn, and what does it cost in partition quality?

## Design

The last snapshot of each calendar day from 07-18 to 08-13 gives ten corpora
(n 277→667, k 12→18, live-embedding coverage ~100%). Per seed, two chains
over the same corpora:

- **cold** — production behavior: fresh `KMeans(n_init=10)` every day. Seed 0
  *is* production (`random_state=0`); the other 19 probe init sensitivity.
- **warm** — identical day 0, then each day inits from the previous day's
  fitted centroids (farthest-point-extended when k grows), `n_init=1`.

Consecutive partitions run through the real `identity.reconcile`, centroid
fallback included, so the outcome metric is the production event count itself.
Guards: silhouette (cosine), inertia, and max cluster share — the 2026-07-17
sample-weight collapse is the reason quality is measured, never assumed.
20 paired seeds; all intervals are bootstrap CIs on per-seed paired deltas.

## Figure 01 — the trade

Left: each seed's chain-mean events per transition, cold → warm — twenty
paired lines collapsing from 6.3-9.1 onto 0.67. Middle: where the churn
lived — under cold refits **49% of notes change theme lineage every day**
(the matcher was heroically relabeling noise); warm chains sit at 2.6%, and
their only bumps are k-growth days. Right: the price — warm inertia runs
+1.4% over the cold optimum and creeps to +1.9% by day ten, never touching
cold parity.

The event-kind breakdown says what survived: cold's 9 transitions produce
births, deaths, merges, splits and restatements in bulk (1437 events across
all seeds); warm produces **only births, exactly at k jumps** (120 = 20 seeds
x 6 new clusters). The honest signal — the taxonomy growing — is the only
thing left.

| metric (chain mean) | cold | warm | paired delta [95% CI] |
|---|---|---|---|
| events / transition | 7.98 | 0.67 | −7.32 [−7.64, −6.97] |
| note lineage churn | 49.0% | 2.6% | −46.4pp [−47.3, −45.3] |
| silhouette (cosine) | 0.039 | 0.037 | −0.002 [−0.004, +0.000] |
| inertia | 363.5 | 369.6 | +1.7% (day 10: +1.9%) |
| max cluster share | 10.6% | 15.5% | +4.9pp [+4.0, +5.8] |

## Limits

- **Ten days is not a year.** The inertia gap creeps monotonically
  (+1.38% → +1.94%); nothing here bounds where it plateaus. A production
  adoption would want a periodic cold re-anchor or a hybrid init (fresh
  candidates plus the warm one, best inertia wins) — the hybrid would
  reintroduce churn exactly on the days it improves the optimum, which may be
  the correct behavior.
- **Max share drifts up** (10.6% → 15.5%): the biggest cluster fattens. This
  is the direction of the 07-17 collapse at mild scale — 103 notes of 667,
  not two blobs — but it is the number to watch if the horizon extends.
- **Lock-in is the mirror risk of stability.** Warm chains never reorganize;
  the inertia guard says the data did not demand reorganization in this
  window, but a genuine taste restructuring would surface later or slower
  under warm inits. The grove made this same trade deliberately (cached
  topology, incremental attach); the profile has not yet.
- Corpora are historical member sets under **today's** embeddings — same
  encoder epoch as every production run since 07-17, but not a byte-level
  replay of those runs.
- Adoption reshapes shared geometry: grove, map and the portrait consume the
  same clustering. This section sizes the trade; it does not take it.

Compute: `experiments/warmstart_identity.py` →
`warmstart_identity_results.json` (commit-stamped). Figure:
`scripts/plot_warmstart.py`.
