# The experiment record — index to `docs/assets/`

The project is `ytk`, my personal knowledge system: it ingests YouTube videos,
Instagram posts and web articles into an Obsidian vault — a folder of markdown
notes — enriches them with a language model, and indexes everything for
semantic search. Roughly half the sections below are about rendering that
collection as a 3D map; the other half are about measuring whether the
collection's structure is real. Each section stands on its own and defines its
own terms; a few recur often enough to name here. The **corpus** is the set of
notes being measured. An **embedding** is the vector a text encoder produces
for a note, and **cosine similarity** between two of them is the usual stand-in
for "how related are these". **The cone** is this corpus's most consequential
geometric fact, found in section 12: every note leans in one shared direction,
so a large part of any two notes' apparent similarity is something the entire
collection has in common. **The gate** is the automated retrieval check that
nothing ships past. And a **null model** — the thing that turns most of these
numbers into findings — is the same measurement run on deliberately meaningless
data, so a score has something to be compared against.

`docs/assets/` is the chronological visual-experiment record of this project:
thirty-three numbered sections, each one folder with one `README.md`, holding the
figures, animations, sidecar data and working notes for a question that was
actually measured. The order is the order the work happened in, which is the
point — early sections do not know what later ones found, wrong predictions
stayed on the page, and the corrections are annotated in place rather than
edited away. Every section is reproducible from a script in `scripts/`, every
number was measured against real data, and no figure was redrawn to agree with
a later result.

Two files in `docs/assets/` are not sections:

- **[`docs/assets/README.md`](assets/README.md)** — the visualization
  house-style contract, and it is binding rather than advisory: design intent
  (maximize visibility and expression, geometry over labels, self-reporting),
  the palette with what each colour means, composition and framing rules, the
  manim cairo traps, and the checkpoints-vs-assets split. Read it before
  drawing any figure or chart anywhere in this repo.
- **[`docs/assets/README-two-lenses-program.md`](assets/README-two-lenses-program.md)**
  — the reconciled ledger for sections 22-25, re-read from the artifacts on
  disk and cross-checked across sections. Where those four sections disagree,
  the ledger is the arbiter. **Start there for anything about the two-lenses
  program.**

## The sections

| # | section | what it asked | what it found |
|---|---|---|---|
| 01 | [fog](assets/01-fog/README.md) | can the knowledge map's density field be rendered, and its filaments traced? | predictor-corrector ridge tracing turns 27 chained fragments into continuous strands; 98.3% of 4,067 notes sit within 2h of a 225-vertex skeleton (18x compression) |
| 02 | [picking](assets/02-picking/README.md) | does GPU colour-ID picking do what the shader claims, and is it faster? | an independent matplotlib reimplementation agrees with the block read; real headless-Chromium runs measure idle FPS and hover cost before and after |
| 03 | [flow-pulses](assets/03-flow-pulses/README.md) | what wavelength and speed should the strand pulse use? | one line of arithmetic over walked arclength; motion verified by pixel-diffing two frames, never by exit code |
| 04 | [ribbons](assets/04-ribbons/README.md) | `gl.LINES` cannot vary width — does the quad-expansion geometry hold on paper? | the vertex shader's screen-space perpendicular expansion recomputed and drawn without a GPU in the loop; density controls width |
| 05 | [bloom](assets/05-bloom/README.md) | is the numpy tuning pipeline a faithful model of the bloom shader? | the numpy side mirrors the shader's own approximations (9-tap kernel, same spacing, same downsample) and is compared against real GPU captures |
| 06 | [semantic-domains](assets/06-semantic-domains/README.md) | is the map's grouping axis a directory axis wearing semantic labels? | measured mass per candidate rule, provenance path slugs against grove buckets, with null-model separation |
| 07 | [time-machine](assets/07-time-machine/README.md) | what do note birth dates look like before a scrubber is built against them? | the distribution vetoes the obvious design — dates are piled at one end of the vault's life, not spread across it |
| 08 | [eval-gate-freeze](assets/08-eval-gate-freeze/README.md) | can the retrieval gate stop measuring corpus growth and start measuring quality? | frozen scoring on a grown corpus, with a deliberately injected regression as the red control |
| 09 | [heatmap-key-moments](assets/09-heatmap-key-moments/README.md) | do Claude-generated key moments land where people actually rewatch? | +0.044 lift over a per-video null (76.3% win rate) and about a third of an uploader's +0.121; the tempting "too many marks dilutes" story was noise (p = 0.060, R² = 0.040) |
| 10 | [tag-coherence](assets/10-tag-coherence/README.md) | do enrichment tags name real categories? | 58 of 69 scorable tags cohere beyond z = 2; the failures are format and utility labels, and `reference` scores z = −3.4 because it describes the reader, not the text |
| 11 | [animations](assets/11-animations/README.md) | can the two overnight experiments be explained in motion? | two manim scenes built entirely from the real sidecars — the size-matched null, and the replay curve |
| 12 | [embedding-geometry](assets/12-embedding-geometry/README.md) | 69 tag concepts in 1024 dimensions — is the space crowded? | not crowded, offset: every note sits at cosine 0.51 from one shared direction, and behind it a genuinely ~104-dimensional cloud |
| 13 | [space-3d](assets/13-space-3d/README.md) | a still 3D scatter is ambiguous — does the claim survive a moving camera? | three orbiting scenes over the same frozen coordinates; the camera is held across the highlight swap so only membership changes |
| 14 | [garden-allometry](assets/14-garden-allometry/README.md) | what scale and branching geometry should the garden trees use? | eight experiments against the real buckets and the renderer's own skeleton dump — taper, trunk allometry, tropism, persistence, roots |
| 15 | [plane-geometry](assets/15-plane-geometry/README.md) | two documents span a plane — is drawing it worth anything? | an arbitrary pair-plane inherits the offset and casts shadows 8.4x longer than chance; fitting axes to the neighbourhood beats picking better points, 3.3x vs 1.7x |
| 16 | [corpus-primer](assets/16-corpus-primer/README.md) | what do "the mean is 11x chance", the participation ratio and z = 17 actually mean? | three pedagogical figures, one concept each, companions to sections 12 and 15 |
| 17 | [corpus-growth](assets/17-corpus-growth/README.md) | do the geometric claims survive 15% more corpus? | the geometry holds (‖mean‖ 0.5104 → 0.5106, tag z at r = 0.984) and the roads do not pave themselves — 75 new notes moved path support by 0.008 |
| 18 | [sae-fingerprints](assets/18-sae-fingerprints/README.md) | can the shared cone, the tags and the roads be read as named SAE features? | the cone is 31 always-on features; 9 of 10 large tags have coherent feature sets; roads read as monotone vocabulary handover (rho = −1.0) — and production search was never touched |
| 19 | [rank-metrics](assets/19-rank-metrics/README.md) | do rank-based metrics beat cosine on an anisotropic space? | the night the null models won: rank metrics lose to cosine, CSLS flattening splits its prediction, and the cross-space correlation is taken back by its own shuffle |
| 20 | [query-spaces](assets/20-query-spaces/README.md) | what queries can a road between two interests express? | the highway runs through the densest country (support 0.750 vs 0.259) with zero bridge stops; no meaningfully weak bridges exist at tag level; extrapolation's usable leash is t ≤ 1.25 |
| 21 | [geometry](assets/21-geometry/README.md) | do toy-model polytopes and road intersections exist at production scale? | the digon: twelve cone features on the 1/2 plateau in six antipodal decoder pairs; 19 notes answer all 45 roads; the roundabout construct killed by its own criterion |
| 22 | [two-lenses](assets/22-two-lenses/README.md) | would a second embedding space see a different person? | yes — the same 532 notes sort by topic in Qwen (purity 0.718) and by register in the SAE space (0.949); side finding, the profile eval carries a ~0.19 noise floor |
| 23 | [style-lens](assets/23-style-lens/README.md) | can a purpose-built style embedder be the voice axis, and does voice survive inside one medium? | StyleDistance is a better and 20x cheaper voice meter with no topic bleed; structure survives inside YouTube, but the two voice lenses then stop agreeing (ARI 0.047) |
| 24 | [native-sae](assets/24-native-sae/README.md) | can a SAE trained on the production space make it natively interpretable? | annotation layer yes, replacement no: the head of the dictionary reproduces across runs and names subject matter, but a reconstructed index fails the retrieval gate at every config |
| 25 | [shared-private](assets/25-shared-private/README.md) | can the two lenses be decomposed into shared, topic-net-of-voice and voice-net-of-topic? | a large real shared subspace (25/25 held-out correlations beat a 200-permutation null) that is *topical*, so stripping it destroys the topic axis instead of de-biasing it |
| 26 | [medium-signal](assets/26-medium-signal/README.md) | does the profile's ranking change when the medium confound is removed from the save signal? | materially — production's #1 theme falls to 11th, 0/1000 medium-preserving shuffles move the ranking as far; the corrected signal shipped as `interest.medium_controlled` |
| 27 | [alpha-sensitivity](assets/27-alpha-sensitivity/README.md) | does the inherited alpha=7 still matter once the signal is medium-corrected? | yes — corrected tau(0,31) = 0.235, alpha<=1 beats 995+/1000 medium-preserving shuffles, 4 of 5 top slots are alpha's to give; the honest refit stays data-blocked (7 cross-source saves) |
| 28 | [honest-ladder](assets/28-honest-ladder/README.md) | the owner's playlist is curated — what happens when that intent is finally recorded? | the alpha thread dissolves: 322 "passive" YouTube notes were deliberate, honest tau(0,31) = 0.882 inside its own shuffle band, max share move 0.006; `medium_controlled` retired, playlist cache + coverage guard shipped |
| 29 | [planet-continents](assets/29-planet-continents/README.md) | can `/orb`'s radial layout be de-overlapped without destroying its continents? | yes, nearly for free — tangent repulsion converges by 40 iterations to 0% buried at the render threshold, keeping 49.7 of 52.2 points of ocean, silhouette 0.108 of 0.117, anchor 1.000, trust 0.8626 of 0.8646; slot-assignment k4 is second, every haversine arm dominated; the legacy `score()` gate measures a threshold the renderer doesn't draw (its theta 4.19° vs `TILE_HALF` 3.15°), and satisfying both costs a measured 4.6 points of ocean |
| 30 | [coastlines](assets/30-coastlines/README.md) | can the planet's land/sea boundary be drawn without a density knob? | yes — E29's ocean calibration is a contour level, not just a scalar: the coast is the iso-distance line at 5.09°, land covers 48% of the sphere, and the 32 wrap-aware continents name themselves from tile themes (the largest, 30% of the sphere, is agentic coding + systems engineering; discipline/self-taught learning is its own continent) — `continents.json` ships for a future /orb layer |
| 31 | [theme-planets](assets/31-theme-planets/README.md) | does each theme deserve its own survey, and how do sibling planets stay visually distinct? | refit beats slice on all five top themes (mean trust +0.039) so the #78 recursion justifies per-planet refits; refit worlds are Pangeas (71-85% land) while slices keep more ocean; the Sudarsky-translated taxonomy (activity→class, cohesion→saturation, n^(1/3)→size) degenerates on the top five — all hot, Batalha's caution realized — so size and saturation carry the separation |
| 32 | [galaxy](assets/32-galaxy/README.md) | does the sky over the theme planets need its own de-overlap pass, or is the centroid layout already legible? | the galaxy is free — planet centroids under the map's own projection hold hidden disc area under 5% up to K* = 3.00° per n^(1/3) (the tile-size floor is 1.34°), with map agreement rho 0.710 clear of the shuffled null (0.139) and the self-fitted control's floor (0.482); spreading (B) buys a near-triple sky (K* 8.50°) at measured anchor cost; the mid-tail delivers classes III and IV but 16 of 18 planets are still class V — `galaxy.json` ships arm A |
| 33 | [channels](assets/33-channels/README.md) | which orbital channels — moons, rings, spin — carry real structure, when each must beat its own null before it renders? | moons: 9/18 planets reproduce internal hierarchy geometry but only 2 bear a discrete satellite (gradients-not-clusters, one level down); rings: 8/18 earn a partner pair against the per-planet max-z permutation null (strongest: neural network geometry → transformer internals, z 13.4) after the registered share-gate was reported as inverted by construction; spin: 4/18 outside their date-permutation band (the two dormant are exactly the class III/IV worlds) and independent of hue (rho −0.45) — `channels.json` ships exemplar-backed moons so the build can draw them as thumbnails |
| 34 | [individual-lens](assets/34-individual-lens/README.md) | can a single real note carry a finding the record has only stated statistically? (three remixes in the Welch Labs grammar, after studying "The Dark Matter of AI") | yes, with a disclosed readout: seriated by corpus \|mean\|, one note's row profile exits the random-order null band (rows 0-2 mean 0.037 vs ±0.02) and centering flattens it to 0.0015 — but in native order the cone is invisible, the checkpoint that shaped the section; the video's own note traced end-to-end is a typical citizen (L0 5370 vs median 5282) whose loudest SAE feature is "CNN capabilities" and whose neighbors are its own reference list; the ai-agents→machine-learning road drawn as deltas-from-start shows top-1 changing hands 4x with no bridge spike — a handover, not a fade; figure 04 stands the same field up as terrain (height instead of brightness): the mean is a ramp, the note is weather on the ramp, and centering removes the ramp but not the weather |
| 35 | [the-knob](assets/35-the-knob/README.md) | do section 24's exemplar-named latents actually steer retrieval when clamped — the video's intervention loop run on the production space? | asymmetrically: clamping latent 977 "EpicMap" into an unrelated philosophy query takes over the top-10 (0% → 30% at 0.5x its corpus max, 90% at 1x, saturated at 2x onto a single attractor note — the babble analog); but on a genuine EpicMap query where 977 is the loudest latent, killing it — or its whole family, or all eight loudest — leaves retrieval EpicMap (1.0/1.0/0.6): the knob adds the concept but the concept is not the knob; and 21's cos −0.99 antipodal decoder pairs, invisible in native order, become mirrored gradients + an anti-diagonal scatter once seriated |
| 36 | [six-rulers](assets/36-six-rulers/README.md) | what do 19's six metrics do to one concrete note — the corpus's biggest hub? | the hub ("Turn Claude Into A Design GENIUS...", in 63 of 568 top-10 lists) keeps its own neighbours under every ruler (L1/Spearman 10/10, centred 9/10, CSLS 7/10) while its ubiquity collapses under any cone-removing transform — centring alone halves it (63 → 27), CSLS cuts it to a third (21): hubness rides on the cone, not just on CSLS's fix; the six full 568×568 matrices under one shared seriation show the same blocks in every panel — the rulers disagree about the background light, not the map |
| 37 | [two-families](assets/37-two-families/README.md) | 22 said the two lenses file notes differently — what does that look like for one note you can read? | "A New Era of Python GUIs", picked by rule (zero neighbourhood overlap, strongest own-family cohesion): its Qwen family is marimo posts and agentic-coding notes (topic — two share its exact theme), its SAE family is LangGraph/p5js/Electron/TouchDesigner tutorials (register — each annotated with its shared named feature); zero notes in both lists, and the corpus median overlap is 3/10, so the drift is the ordinary condition, not a stunt |
| 38 | [warmstart-identity](assets/38-warmstart-identity/README.md) | #83's threshold sweep ended on a ceiling — 5-7 lifecycle events on quiet days come from the KMeans refit itself; does warm-starting the daily refit from yesterday's centroids remove them, and at what cost? | 12x: 8.0 → 0.67 events/transition and 49% → 2.6% daily note-lineage churn (20 paired seeds, 9 real transitions through the production `identity.reconcile`), with warm's only surviving events being births at k-growth days — the honest signal; the price is inertia +1.4% creeping to +1.9% over ten days, silhouette −0.002 on 0.039, and max cluster share 10.6% → 15.5% (the 07-17 collapse direction at mild scale); ten days bounds nothing long-run, lock-in is the mirror risk, and adoption reshapes the geometry grove/map/portrait share — the section sizes the trade, it does not take it |
| 39 | [trace-inventory](assets/39-trace-inventory/README.md) | #96 rung 1: before designing telemetry, what do the traces the brain already leaves actually hold? | a census of seven traces and the first acceptance report: the 60k-row retrieval log is 98.6% the system examining itself (1904 eval replays, 152 pipeline bursts, 137 smoke probes, 76 fixtures) and the residue is 33 genuine searches in 15 days — 21 agent-confirmed, 0 from the hub (2 hub searches ever typed, both predating the log); capture outruns genuine search 18:1 (554 hub captures, one 344-event bulk-drain day disclosed), 55 of 671 notes were ever served to real demand while 153 were read inside Claude sessions via unlogged vault_read; the vocabulary corrections found, not guessed: actor needs user/agent/system, zero-result searches are never written, the agent's dominant access path is invisible to ytk, and instrument traffic must self-identify at write time |
| 40 | [reuse-ladder](assets/40-reuse-ladder/README.md) | #96 rung 2: was anything captured ever reused — and through which channel? | yes, and through the channel nobody instrumented: 45 elective source-note-reading sessions since May (57 distinct source notes), 26 of which modified work outside the vault, with the mass in the last five weeks — while the "strongest" channel the issue named, brief citations, holds 1 source-note reference across 56 briefs (briefs describe work produced, not knowledge consumed); two corrections drive every number — session-level joins (observation level shows 49/55 vault-housekeeping) and ritual-vs-elective reads (pooling inflates reuse 3x, 125 vs 45 sessions); the fix that turns the emptiest rung into the strongest is free: the brief template asks for sources consulted; outcome model v0 written from these baselines at docs/telemetry-outcome-model.md |
| 42 | [atlas-inventory](assets/42-atlas-inventory/README.md) | #183 rung 0: before the activation atlas builds anything, do its inputs exist, how far do they reach over today's corpus, and which latent is the protagonist? | every input exists: 12.1% of the 18,755 live vectors postdate the Aug-8 SAE checkpoint (kept for rungs 0-5, per the epic's lean — every cell will disclose its OOD fraction), segments cover 99.5% of video notes, thumbnails 11.7% of map points so the wall will be mostly `[T]` tiles; the native dictionary has no cone — zero dead latents, zero always-on, the widest latent reaches 15.8% of the corpus and the median serves 218 documents, so section 18's 31-latent subtraction list dissolves into the excess-over-base-rate null; the protagonist, announced by measurement: the AlexNet note's loudest latent is #1597 "educational breakdown of language model mechanics" (activation 0.219, 1.9% breadth, named through the head's own Haiku pipeline), runners-up #1211 sparse-autoencoders-and-interpretability and #1310 transformer-architecture-and-tokenization |
| 43 | [feature-wall](assets/43-feature-wall/README.md) | #183 rung 2: are the top-100 latents coherent objects that survive retraining — and how much of their evidence can be pictures? | the head is the stable part of the dictionary: 59/100 survive retraining at decoder cosine 0.8 and 89/100 at 0.5, against 7% and 20% over the full 2048 — frequency buys stability, and every tile wears its own badge; the wall's evidence is 55.9% real thumbnails (rung 0's map-coverage number predicted mostly-`[T]`, but head exemplars skew to YouTube segments); the coherence null makes the names' grounding visible — each latent's own exemplars read as one topic while shuffled assignment reads as the corpus, with the protagonist's tile (badge 0.57, stated like everyone else's) outlined in its CYAN thread |
| — | [memory-field](assets/memory-field/README.md) | what is the free baseline on memory-capture data quality? | rung 0 of #150: duplicate density, timestamp integrity, memo bursts with launch-day test traffic named in the caption, plus the E- and R-series follow-ups |

## Reading paths

**How the map is rendered** — 01, 02, 03, 04, 05, 07, then 14 for the garden.
Start with the fog and its filament tracing, then each shader feature and its
independent witness. The recurring lesson is the method, not the effect: never
trust only the renderer you also wrote, and verify motion by pixel-diff.

**Does the embedding space have structure** — 10, 12, 16, 15, 17, then 21.
Tags first, because they are the ground truth everything else is scored
against; then the cone that was distorting the tag numbers; the primer if the
statistics need unpacking; the plane as the consequence for drawing; growth as
the out-of-sample test; and 21 for the geometry at the far end.

**The two-lenses program** — read
[the ledger](assets/README-two-lenses-program.md) first, then 22, 23, 24, 25,
26 in order. The ledger carries the reconciled numbers and the two corrections
the sections themselves could not make; the sections carry the method and the
caveats; 26 is the close-out that turned the program's confound into a
production fix, and 27-28 are the aftermath: 27 measured the one thread 26
left open and recorded it blocked; 28 dissolved it by recording the intent
the pipeline had never written down, and retired 26's correction with its
job done.

**How this project decides things** — 08, 09, 18's pre-registration section, 19,
20, 21. The gate that stops growth being mistaken for quality, the null model
that turns a number into a finding, the registered predictions, and three
sections where the registered prediction lost and the loss was published with
the same prominence as a confirmation.

## Corrections and supersessions

Every retroactive annotation inserted into the record, newest evidence last.
Each is a blockquote in the affected section, marked **Later:**, sitting
alongside the original claim — which was never edited.

- **08** ← 24. An independent numpy mirror of the ranking reproduced the frozen
  baseline exactly, then rejected an SAE-reconstructed index at every config.
- **10** (`reference` z = −3.4) ← 12. Centred, `reference` scores positive; the
  stable reading is the observed +0.003, orthogonality rather than
  anti-correlation. Both geometries agree on the substance.
- **10** (the merge list) ← 12. Recomputed on centred vectors the merge
  conclusion holds but the numbers were inflated: ~0.93 not >0.97, the order
  shifts, and `education + learning` drops out.
- **10** (the z ranking) ← 17. Re-measured after 15% growth: r = 0.984, mean
  |dz| 0.56, only boundary crossers. The "one corpus" caveat is now tested.
- **12** (participation ratio 104) ← 17. Not an encoder ceiling but an n-limit;
  at matched n = 493 the grown corpus measures 103.6.
- **12** (centring as an actionable retrieval result) ← 19. Measured at +1.2 on
  tag-match@10 — the only gain anywhere — but it did not clear the registered
  bar, so production search stays cosine and the question stays open.
- **17** (hubness is mild) ← 21. On tag-centroid roads the regime inverts: 19
  notes answer all 1215 stop slots, the top one serving 37 of 45 roads.
- **17** (the E6 duplicate wrinkle) ← 19.3. Duplicates here are re-ingestions
  with different enrichment texts, so geometry cannot catch them; dedup must
  use content identity.
- **18** (the whole gemma instrument) ← 22, 24. The fingerprint space sorts by
  register and medium, not subject; "the corpus voice" is literal. A natively
  trained SAE reads subject matter instead.
- **18** (full-corpus coverage) ← 25. The corpus-wide rebatch failed twice, so
  22-25 all run on 532 of 604 themed notes; the instrument aged exactly as 18
  warned it would.
- **18.5** (monotone handover) ← 21.4. The single-crossing premise does not
  generalize — 31 of 45 roads — so handover is a per-road readout, not a law.
- **18 pre-registration, 18.4b** ← 19. The bar was cleared at r = 0.832 and the
  control collapsed at 0.757; the interpretation was withdrawn.
- **18 pre-registration, 19.1** ← 19. Failed: rank metrics lose to cosine, no
  metric cleared 2 points, Phase B not earned.
- **18 pre-registration, section 20** ← 20. 20.1(c) failed (zero bridge stops),
  20.2 confirmed at exactly the bar, 20.3 failed with the leash measured at
  t ≤ 1.25, 20.4 failed and the empty acquisition list is the answer.
- **18 pre-registration, 21.2** ← 21. The skeptical registration lost: twelve
  features on the 1/2 plateau in six antipodal pairs, against a null of zero.
- **18 pre-registration, 21.4** ← 21. Killed by its own criterion, 31 of 45.
- **19.1** (the failure) ← 22. Given a mechanism: "a space organized by voice
  cannot find topical neighbors across media."
- **20.1** (the itinerary as artifact) ← 21. That itinerary's first stop is the
  note serving 37 of 45 roads; a tag-road overlay would funnel everything
  through the same interchanges.
- **22** (the 0.335 "measured ceiling") ← 25. One draw from a 0.31-0.48 band;
  "% of ceiling" readings retracted, the direction of the gap kept. *(This
  annotation predates the pass and was reformatted for consistency.)*
- **22** ("the SAE lens reads how it speaks") ← 23, 25. Most of that agreement
  was the medium; strip it and the two voice lenses disagree. The shared
  subspace is overwhelmingly topical.
- **23** (34% and 71% of ceiling) ← 25. Same retraction: the ordering stands,
  the ratios do not.
- **24** (the deliberate-save confound) ← 25. The prediction it generated — that
  shared structure would be medium — is refuted; medium is one dimension of 25,
  and it reads as document furniture.
- **ledger** (doors now open: the r-label confound, E4 redesign) ← 26. Both
  closed: the confound measurably owned the profile ranking, and the corrected
  signal shipped; what stays open is alpha's own fit target.
- **ledger** (still open: alpha's own fit target) ← 27. Measured rather than
  refit: the corrected ranking is still alpha-sensitive beyond its
  medium-preserving null, so the inherited slope does real unjustified work —
  and the refit itself is data-blocked until deliberate saves exist that are
  not collinear with source.
- **26** (alpha fitted against the confounded target) ← 27. The sweep answers
  it: sensitivity survives the correction; see section 27 for the verdict and
  the unblock conditions.
- **26** (`medium_controlled` as the production fix) ← 28. Retired, job done:
  with playlist intent recorded on the YouTube side, the subtraction would
  re-create the confound mirrored. The medium repair it bought is preserved
  by honest bookkeeping (YouTube pays 0.73 of the top-5 under both).
- **27** (the refit as a blocking prerequisite, "years, not weeks") ← 28.
  Dissolved rather than unblocked: the "passive" corpus was 322 curated
  playlist adds the ladder never recorded. With r near-uniform, alpha cancels
  out of the shares (tau(0,31) 0.882, inside its shuffle band) and there is
  no ranking-relevant slope left to fit.
- **30** (the coast is parameter-free) ← 30, figures 04-07. The deferred
  cosmetic option was exercised same-day on the owner's circle verdict: the
  default rule is now the organic composite (metaball softmin, warped
  domain, Perlin fBm), land area still pinned by the E29 calibration, the
  hard contour kept as `--coast hard`, and a `--shuffle-seed` that rerolls
  the shoreline without moving a tile. One instrument correction inside:
  box-counting fractal dimension is invalid on an archipelago (disconnected
  islands collapse to lone boxes; D came out below 1) — the committed
  numbers use the Richardson divider on the longest single coast.

- **33** (the registered ring share-gate) ← 33, same-day. The #178 gate
  compared each planet's cross-theme NN share against full label
  permutations — a null that destroys all coherence and therefore sits near
  1, so the observed share can only fall below it. Its 0/18 is a theme-
  coherence confirmation, structurally unable to detect a ring. Reported in
  the section, replaced by the per-planet max-z pair-excess gate; the
  registered result ships alongside the corrected one in `channels.json`.

One program-level correction has no earlier section to annotate, and is
recorded here instead. Section 24 found the deliberate-save label is a
disguised medium label — `ytk/signals.py` assigns r ≥ 1 from the source folder,
so every r ≥ 1 note is Instagram/TikTok/web and every r = 0 note but seven is
YouTube. Any pipeline weighting by r-levels is partly weighting by medium,
**the profile's alpha = 7 signal weighting included**. No section in
`docs/assets/` leans on r-level weighting, so nothing here needed annotating;
the implicated consumer is the profile pipeline, and the open question is
carried in
[the two-lenses ledger](assets/README-two-lenses-program.md). Section 26 then
closed it: the ranking the profile renders was substantially the medium's
(0/1000 medium-preserving shuffles reproduce the movement), and the corrected
signal now feeds the weight path in production.
