# The Gemma instrument — formal conclusions (sections 18-21)

What running Gemma 2 2B + Gemma-Scope SAE fingerprints over the corpus
bought, what it did not, and how the backlog moves. Verdict-level detail
lives in `notes.md`, `preregistration.md`, and `../21-geometry/notes.md`;
this is the ledger.

## Gained — validated facts

1. **The cone is nameable.** The shared offset every note carries
   (norm 0.51 in Qwen space) reads as 31 always-on SAE features: technical
   register, code structure, proper nouns, discourse scaffolding (18.3).
   The corpus-wide anisotropy is not noise; it is the shared voice of the
   collection, and it now has a feature-level inventory.
2. **The cone has internal geometry.** Six antipodal decoder pairs put
   twelve of those 31 features exactly on the 1/2-dimensionality plateau —
   the toy-model digon, in production decoders (21.2, against the
   registered skeptical prediction). Hypothesis on record: always-on
   antipodal pairs are signed axes, so the cone may carry ~6 bidirectional
   dimensions rather than 31 independent ones.
3. **Tags are feature vocabularies.** 9 of 10 large tags have coherent
   differential feature sets (18.4); the tag-pair z-vector cosines track
   Qwen centroid cosines only weakly and the shuffle control took back the
   headline correlation (18.4b) — recorded as the honest boundary of the
   claim.
4. **Roads read as vocabulary handover.** Perfectly monotone on both
   registered roads (rho = -1.0; 18.5, 20.1); the single-crossing premise
   does not generalize to all 45 tag pairs (21.4 kill), so handover is a
   per-road readout, not a universal law.
5. **Instrument discipline, earned twice.** Auto-names are unreliable until
   token-probed (drug-usage/privilege mislabels); comparisons must be
   pool-matched (the 18.1 false kill); sum pooling and top-256 mass
   presence are the recorded conventions.

## Gathered — artifacts now on disk

- `fingerprints.npz`: 568 x 16384, sum + max pooling, fp16, sha256-stamped
  manifest; full-corpus coverage against the live store after the #164 fix.
- `cone-features.json`, `tag-regions.json`, `road-diffs.json`,
  `../21-geometry/cone-decoder.npz` (the 31 decoder rows), plus the
  validated local rig (`sae_rig.py`, `sae_batch.py`) and figures for every
  claim.
- A working Neuronpedia API playbook (search-all needs sortIndexes; feature
  batch naming; token-level activation probes) in `landscape.md`.

## Unlocked — possible now, not yet built

- **Feature lanes on the road itinerary**: name what changes along a path
  (18.5's verdict: lanes name the change, narration says what it means).
  Blocked only on serving a fingerprints sidecar — the wheel does not ship
  the npz.
- **Corpus-quality scanning by feature**: rank notes on the cookie-policy
  feature to find boilerplate contamination retroactively (#167); the
  fingerprint matrix doubles as a data-quality instrument.
- **Signed-axis probing**: token-level tests of the six antipodal pairs —
  the cheapest next interpretability experiment with a real payoff for
  understanding what the corpus voice is made of.

## What it did NOT change

- **Production search is untouched.** The 19.1 gate was not met; cosine
  stays; the retrieval eval baseline was never re-stamped. No Gemma-derived
  signal is in any ranking path.
- **The hub shipped nothing Gemma-dependent.** The /map road layer runs
  entirely on Qwen embeddings.

## Backlog deltas

- **#166 (duplicate audit)** — strengthened: content-identity dedup is now
  a measured necessity (19.3), and the ingest-time guard has a concrete
  mechanism.
- **#167 (boilerplate)** — strengthened: gains a retroactive detector, not
  just an ingest-time strip.
- **#168 (tag consolidation)** — strengthened: near-synonym evidence now
  comes from two independent instruments (centroid cosine + feature-set
  coherence).
- **#164 (two-store fork)** — unchanged, still gate-gated; the incident it
  caused (127 skipped rows) is why the batch has a manifest.
- **New, unfiled, deliberate**: fingerprints sidecar serving (decide when
  lanes are wanted); antipodal-pair probing (research, no issue needed);
  re-batch cadence for new notes (the npz freezes at 568 — an incremental
  append using the manifest hashes is the obvious design).
- **Parked by evidence**: any roundabout-style UI construct (21.4 kill);
  tag-level road overlays without interchange dedup (21.3: 19 notes answer
  everything).

## Which existing features improve or get worse

- **Improved (evidence, not code)**: triage of corpus hygiene now has
  ranked, mechanical detectors; road narration has a validated
  complementary readout waiting on serving; tag cleanup has a defensible
  merge list source.
- **Unchanged**: search, dive, feed, profile, quiz — by design, since the
  eval gate said no.
- **Worse: nothing in product.** The costs are operational: a full
  fingerprint refresh is ~2.5h on MPS for the current corpus, coverage
  freezes at batch time, and every conclusion above is stamped to the 568
  notes and the v2 Qwen epoch — growth silently ages the instrument until
  a re-batch.
