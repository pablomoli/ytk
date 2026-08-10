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
twenty-eight numbered sections, each one folder with one `README.md`, holding the
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
