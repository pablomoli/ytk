# External review handoff: grove E2 (data-native trees)

You are an external reviewer. You did not build this and owe it nothing.
Your job is to attack the methodology, statistics, code, and design
decisions below, then answer in the exact JSON schema at the end. Endorse
only what survives your best attempt to break it. You have repo access
(run from the repo root, `/…/ytk`); every referenced path is relative to
it. Python entry points run via `uv run --extra dev python -m <module>`;
the test suite is `uv run --extra dev pytest tests/ -q` (409 tests, green
at handoff time).

## 1. What this is

ytk is a personal knowledge system: notes and consumed media are embedded
(384-dim, `thenlper/gte-small`) into chroma (`~/.ytk/chroma`). The grove
(`/grove` on the local hub) renders "one tree per topic the user cares
about." Tonight's session replaced the grove's decorated random BFS
topology with structure derived from the data, experiment-first. The user
directive: "everything based on science and data."

## 2. The original plan vs what happened

The prior session left an experiment plan E1-E7 (vault handoff, summarized
here since you cannot read it):

- E1 signal inventory + temporal split-half stability gate (dispersion,
  intrinsic dimension via TwoNN, cluster grain, drift velocity, burstiness,
  recency, entanglement)
- E2 render HDBSCAN's condensed tree AS the branch topology (the headline)
- E3 hyperbolic embeddings (Poincare/HypHC) as an alternative topology
- E4 sparse autoencoder motifs as branches
- E5 drift + growth replay (Procrustes-aligned monthly centroids)
- E6 neural cellular automata bark (garnish)
- E7 blind readback legibility gate (user matches tree to topic vs
  shuffled controls)

Deviations, each a target for your criticism:

| planned | what happened | stated reason |
|---|---|---|
| domains from `ytk/mapdomains.py` (directory provenance) | user-authored buckets (`~/.ytk/grove_buckets.yaml`, contents in section 5) | 6 of 9 directory-domains were sprints or a 1,491-note `other`; user rejected the axis. Provenance is not topic. |
| E1 full battery | pre-flight only; 1 signal passed (spread, split-half rho +0.90, n=5), burstiness killed (rho +0.09), intrinsic dim ungateable (3 domains with 90+ notes/half) | 4 of 9 groups span <21 days or are undated, so a temporal gate false-passes on them; scalar yield too thin to drive 10 distinguishable trees |
| E2 HDBSCAN condensed tree | KILLED; replaced by average-linkage agglomerative on cosine, native space | HDBSCAN cannot reproduce itself on random halves in 384 dims (transfer ARI 0.08-0.34); agglo-cosine 0.749/0.880 on the same halves |
| E3 | not run | shootout set a high bar (0.75-0.88); E3 must beat it under the same gate to earn its complexity. Deferred, not refuted. |
| E4 | parked by user (4.6k notes, dead-latent risk) | user decision |
| E5 | blocked | 4 buckets undatable; content dates are upload dates, not ingest dates — replay would animate a falsehood |
| E6 | not run | explicitly "after E1/E2" garnish |
| E7 | next open item | the topology it gates now exists |

## 3. Claims to attack (with evidence locations)

C1. **Directory provenance is the wrong grouping axis; authored buckets are
    right.** Evidence: bucket census (docs/grove-lab/bucket-census.png,
    regenerate via `scripts/grove_lab/report_figs.py`).
C2. **Chroma double-indexes 3.6% of the corpus** (168 phantom vectors;
    instagram worst; youtube-channel was 43 rows / 23 notes). Fix at
    resolve time: `dedupe_indices` in `scripts/grove_lab/buckets.py`;
    GitHub issue #71. All report numbers are post-dedupe.
C3. **Burstiness fails a temporal gate and its random-split "pass" is an
    artifact** (thinning a point process preserves interevent structure, so
    a random control leaks). Temporal rho +0.09 vs random +0.98.
C4. **HDBSCAN condensed trees are unusable as topology source here.**
    Cross-half transfer ARI, mean of 2 runs, random halves:
    epicmap 0.081 / ai-building 0.095 / visual-craft 0.343. Its temporal
    ARI equals its bootstrap ARI on epicmap (0.193 vs 0.187) = estimator
    noise, not drift.
C5. **Average-linkage agglomerative on cosine is stable where structure
    exists**: ai-building 0.749, visual-craft 0.880 (random halves);
    visual-craft 0.816 temporal. Method in `scripts/grove_lab/dendro.py`
    (`fit_nodes`, `_formation_heights`).
C6. **epicmap (2,066 session summaries) has no reproducible sub-structure
    at any granularity** (agglo k=3..12: ARI 0.16-0.25). Its rendered
    branches are cached decoration and labeled as such. Corollary: the
    map's 23 epicmap "workstreams" (`scripts/build_map.py` per-domain
    UMAP+HDBSCAN) are likely also decoration.
C7. **ai-building temporal (0.214) vs bootstrap (0.749) is drift, not
    noise**, acceptable for a grow-only cached tree.
C8. **Grow-only cache** (`~/.ytk/grove/{bucket}.tree.json`): incremental
    nearest-centroid attach; `--rebuild` anchors node ids by member-overlap
    Jaccard >= 0.3, greedy best-first. It survived the HDBSCAN-to-linkage
    method swap without renumbering. Known gap: attach never splits a
    branch.
9. **Renderer mapping is honest**: limb length = normalized dendrogram
    persistence; girth = da Vinci area rule on note-mass shares
    (child weight = parent x sqrt(mass share), clamped 0.3-0.92); tree
    scale = sqrt(bucket n). `web/src/lib/grove/datatree.ts`.

## 4. Weaknesses the author already sees (go further)

W1. **The shootout metric may favor the winner.** Transfer ARI assigns the
    held-out half by nearest cluster CENTROID — a spherical-compactness
    assumption that suits linkage clusters and penalizes HDBSCAN's
    density-shaped clusters. A fairer transfer (e.g. kNN assignment) might
    narrow the gap. The epicmap null is metric-independent (all methods
    fail), but C5's margin could be inflated.
W2. n=9-10 groups everywhere: size-confound checks (spread rho -0.30,
    ID rho +0.31, both p>0.4) are underpowered, "not detected" only.
W3. Shootout used 2 random-half runs per cell; no variance reported.
W4. k_main = clip(n//80, 3, 9) and sub-split thresholds (60 notes, k_sub
    <= 5) are heuristics, not swept; stability was checked at other k for
    epicmap only.
W5. Half-fits see half the data; linkage trees on halves may differ from
    the full-data tree in ways transfer ARI does not capture (label
    agreement is not tree-structure agreement; no tree-edit-distance).
W6. Intrinsic-dimension estimates (TwoNN at fixed n=90) were directionally
    interesting (ai-building ~12 vs config ~2.4) but shelved; possibly
    salvageable with better pooling.
W7. Renderer choices (golden-angle forks, step counts 3-12, ring layout)
    are aesthetic, untested against E7-style legibility.
W8. Session-memory text is claude-mem-generated summaries — the embedding
    space itself may be too template-driven for sub-structure to exist in
    ANY project bucket; ai-building's structure may come mostly from its
    consumed-content minority.

## 5. Artifacts not in the repo (inlined)

`~/.ytk/grove_buckets.yaml` (user-authored; drives everything):

```yaml
version: 1
seed_floor: 0.62
buckets:
  - name: epicmap
    projects: [epicmap]
  - name: ai-building
    projects: [ytk, tts, observer-sessions, config, scheduler]
    themes: [AI-augmented building]
    paths: [second-brain/projects/ytk]
  - name: youtube-channel
    paths: [second-brain/projects/youtube-channel]
  - name: visual-craft
    projects: [coolshit, render-decomposition, spacecraft]
    themes: [Visual math & 3D craft]
  - name: playful-tools
    themes: [Playful creative tools]
  - name: mind-systems
    themes: [Mind & productivity systems]
  - name: combat-sports
    themes: [Combat sports & S&C]
  - name: eating
    themes: [High-protein practical eating]
  - name: film
    themes: [Film criticism & craft]
  - name: adhd
    themes: [ADHD & masking]
```

Snapshot schema (`~/.ytk/grove/{bucket}.tree.json`): `{version,
bucket, embedding_model, built, n_notes, params:{kind, method, k_main},
stability:{kind: temporal|bootstrap, ari, span_days}, nodes:[{id, parent,
mass, persistence, centroid[384], exemplars[<=3]}], members:{note_key:
node_id}}`. Per-bucket gates at handoff: epicmap 0.278 temporal (noise);
ai-building 0.214 temporal (drift); visual-craft 0.816 temporal (pass);
youtube-channel + 6 interest buckets below the 30-note clustering floor
(saplings, single-node topology).

## 6. File inventory

Lab (new tonight):
- `scripts/grove_lab/buckets.py` — bucket load/assign, corpus dedupe, coverage CLI
- `scripts/grove_lab/dendro.py` — linkage topology, stability gate, grow-only snapshot cache
- `scripts/grove_lab/report_figs.py` — census + temporal figures
- `tests/test_grove_buckets.py`, `tests/test_grove_dendro.py` — unit tests (TDD)
- `docs/grove-lab/e2-report.md` — the measured report (+4 PNGs alongside)

Hub + renderer (new/modified tonight):
- `ytk/ui/server.py` — `/api/grove` (search `_GROVE_DIR`); tests at bottom of `tests/test_hub.py`
- `web/src/lib/grove/datatree.ts` — topology -> TreeNode generator (new)
- `web/src/lib/grove/scene.ts` — data-mode planting: ring layout, size scale, camera framing
- `web/src/routes/grove.tsx` — data-trees toggle; variant UI removed (foliage won)

Context (pre-existing, read before criticizing the above):
- `web/src/lib/grove/tree.ts` — BFS generator + geometry pipeline both modes share
- `ytk/mapdomains.py` — the rejected provenance axis
- `scripts/build_map.py` — precedent: loading contract, `anchor_names`, per-domain subtopics your C6 corollary indicts
- `ytk/store.py` — `_TEXT_MODEL`
- `docs/superpowers/specs/2026-07-12-grove-workshop-design.md` — the aesthetic workshop spec
- `docs/session-019-brief.md` — session brief (untracked local file; also in the Obsidian vault)

Commit range for tonight: `5fd825b..HEAD` on master (buckets/dedupe,
topology/cache, hub endpoint, renderer, report, variant removal).

## 7. Required output format

Respond with ONE fenced JSON block, nothing outside it:

```json
{
  "verdict": {
    "overall": "sound | mixed | flawed",
    "summary": "<= 3 sentences"
  },
  "findings": [
    {
      "id": "F1",
      "severity": "critical | major | minor",
      "area": "statistics | method | code | design | process",
      "claim_challenged": "C1..C9, W1..W8, or 'new'",
      "argument": "why the author is wrong or overreaching",
      "evidence_or_repro": "file:line, command, or derivation the author can check",
      "suggested_experiment": "cheapest test that would settle it",
      "confidence": 0.0
    }
  ],
  "missed_opportunities": ["things the plan should contain but does not"],
  "questions_for_author": ["only questions whose answers would change a conclusion"],
  "endorsements": ["claims that survived your attack, with the strongest reason they hold"]
}
```

Severity calibration: critical = a conclusion is wrong or an artifact
drives the result; major = a conclusion is materially weaker than claimed;
minor = hygiene. Rank findings most-severe first. Do not pad: five sharp
findings beat fifteen soft ones.
