# The Welch Labs visual grammar — what "The Dark Matter of AI" gives the record

**Source**: Welch Labs, *The Dark Matter of AI [Mechanistic Interpretability]* (Dec 2024),
ingested 2026-08-12 via `ytk sync` →
`second-brain/sources/youtube/the-dark-matter-of-ai-mechanistic-interpretability.md`.

**Method**: frames extracted at ten key moments and reviewed directly; full transcript
read; 13-agent audit (8 haiku readers over all 34 `docs/assets` sections against the
video's techniques, 5 haiku explorers following the description's reference links).
Every external link cited below was title-verified against the live page — the haiku
explorers earned their pay this time, including on four post-2025 sources.

The video traces one sentence — *"the reliability of Wikipedia is very"* — through
Gemma 2B, layer by layer, until a doubt feature is found, named, and steered. The
interest here is not the subject matter (sections 18–25 already do SAE work on this
corpus) but the visual grammar: how he makes 2304-dimensional objects and a 26-layer
pipeline continuously visible.

---

## The grammar: five techniques

Numbered as used throughout; frame evidence from the extracted stills.

**T1 — Vectors are images.** A 2304-dim residual-stream row is reshaped to 48×48 and
shown as a pixel image; the 16,384-dim SAE feature vector is 128×128, where sparsity
is *visible as darkness* (a purple near-empty field with a handful of bright pixels,
colorbar attached). Three details make this work:

- **The reshape is shown, not assumed.** The dense vector, the "force most terms
  to 0" step, and the reshape arrow all appear on screen before the image is used
  as a character.
- **Dual encoding.** The same object appears as bracketed real numbers *and* as an
  image (embedding vectors shown with actual values: −1.54, −0.24 … with "2304"
  under a brace). The image never floats free of what it encodes.
- **The image becomes addressable.** At 12:30 he prints the activation image as a
  physical photo and hand-annotates single pixels in ink — "1393", "1945" — arrows
  pointing at individual neurons. Addressing a neuron is pointing at a pixel.

**T2 — One concrete example, never switched.** The Wikipedia sentence enters at 2:45
and is still the running example at 21:00 when feature 8249 is clamped. Every
abstraction (attention blocks, unembedding, SAE, steering) is introduced as *something
that happens to this sentence*.

**T3 — Invent a readout for intermediate states.** He does not wait for the output:
the logit lens (unembed at every layer) turns 26 opaque matrices into a watchable
prediction that stays stuck on "very" until doubt appears at layer 21. The lesson
generalizes: when a pipeline is opaque, build an early readout and apply it at every
stage, then *say what the readout hides* (the residual stream changes for 15 layers
without flipping the top token — he states this explicitly).

**T4 — Interventions come in calibrated before/after pairs.** Neuron 1393 clamped to
−160 and +160 (stated as "about twice its observed maximum"); feature 8249 at 100
(coherent steering) and 500 (babbling). The pair *plus the overdose* establishes a
usable dynamic range, not just an effect.

**T5 — Magnitudes are geometric facts.** Matrix shapes drawn to scale, probabilities
as scaled squares next to ranked tokens, real measured numbers on screen (0.0117,
20.21%) — never placeholder symbols where a real value exists.

Two supporting habits: **color as identity** (weight-matrix columns tinted to match
the feature symbols they produce, so the eye tracks an object across representations)
and **the readout list kept on screen** while the vector-image evolves, so cause
(image changing) and effect (ranking changing) share the frame.

## The narrative arc: a visual approach to problems

The transcript's structure, in beats:

1. Behavioral hook (ChatGPT cannot forget a phrase).
2. Punchline shown early (feature steering works), then the whole video is a chain of
   *why is this hard* questions.
3. Commit to one example (T2), build the visual object (T1), invent the readout (T3).
4. **Hit the wall on camera** — "we've reached our first big hurdle": the steering
   neuron max-activates on acronym capitals, not doubt.
5. Introduce theory only when the failure demands it (superposition explains the
   observed polysemanticity — theory as diagnosis, not preamble).
6. Show the failed fix before the working one (2023 forced-sparsity experiment, then
   SAEs).
7. Test the fix on the same example, in the same visual language (feature vector gets
   the same image treatment the residual stream got).
8. End on calibrated honesty: <1% of concepts extracted, steering overdose babbles,
   missing features, cross-layer superposition.

This is close to how the record already writes (walls stay in the READMEs, later
sections annotate rather than rewrite, `verdict()` carries the honest conclusion).
The two beats the record practices less: *inventing a readout mid-problem* (beat 3)
and *never switching examples* (the record's figures switch from aggregate to
aggregate; no figure follows one note).

---

## Where the record stands against this grammar

Reader consensus across 34 sections was lopsided in one direction:

- **Already house law**: T5 is design intent #2 (geometry over labels); T4's honesty
  ("draw the panel that kills your own claim") is written into the style README; DIM
  as the null is his "stated observed maximum" made into a color.
- **The gap**: the record reasons about *populations* — distributions, nulls, Gram
  matrices, z-scores — and almost never shows an *individual*. Across all 34 sections
  the readers found essentially no figure that renders an actual embedding vector as
  an image (T1) and none that traces one note end-to-end (T2). Both techniques were
  proposed as strengthening extensions in 30+ of 34 sections; the only near-misses
  are section 12's Gram-matrix pixel image (a population, not an individual) and
  section 18's per-note fingerprints (ranked lists, not images).

The record shows the forest and proves it is a forest; Welch shows one tree growing.
The two are complementary, and the record has the machinery for both.

## Concepts followed (explorer deep-dive, links verified)

**Superposition and feature geometry** — [Toy Models of Superposition](https://transformer-circuits.pub/2022/toy_model/index.html)
(Elhage et al. 2022). Networks pack more features than dimensions when features are
sparse; learned directions arrange as antipodal pairs, triangles, pentagons —
interference is the dot product between feature directions, and the paper's core
visual is exactly T1+T5: learned feature vectors drawn as 2D arrows whose angles ARE
the finding. Section 21 already found antipodal pairs in the production SAE decoder;
the toy-model geometry figures are its direct visual ancestors.

**The logit-lens family** — [interpreting GPT: the logit lens](https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens),
[logit prisms](https://neuralblog.github.io/logit-prisms/), tuned lens
([arXiv:2303.08112](https://arxiv.org/abs/2303.08112)). The readout works because
residual connections keep a consistent basis; it fails where information is not
linearly decodable in the final basis (the tuned lens trains per-layer decoders to
fix this). Logit prisms decompose the final logits by component — *which* head or
neuron contributed, not just *that* a layer knew. The transferable idea: a readout is
a lens with stated failure modes, not a window.

**SAE mechanics and Gemma Scope** — [Gemma Scope](https://arxiv.org/html/2408.05147):
400+ JumpReLU SAEs (per-latent learned thresholds, L0 penalty) across every layer and
three sites (attention, MLP, residual); ~20% of GPT-3's training compute; served on
[Neuronpedia](https://www.neuronpedia.org/) with max-activating examples, logit
weights, and per-latent activation histograms. Feature validation remains unsolved —
current practice is human raters plus LM-simulated explanations, which is exactly the
gap section 24's exemplar-based latent naming lives in. Tooling:
[SAELens](https://jbloomaus.github.io/SAELens/),
[TransformerLens](https://github.com/TransformerLensOrg/TransformerLens).

**The dark-matter argument, 2024 → 2026** —
[Olah's original post](https://transformer-circuits.pub/2024/july-update/index.html#dark-matter):
SAEs are a telescope; rare features stay dark because sparse activations lack
statistical support, and scaling laws (Gao et al.,
[arXiv:2406.04093](https://arxiv.org/abs/2406.04093)) show no completeness plateau.
Since then: Anthropic's
[global-workspace result](https://www.anthropic.com/research/global-workspace) finds
an interpretable "J-space" covering under 10% of Claude's activity — the 90% dark
fraction now has a measurement; [natural-language autoencoders](https://transformer-circuits.pub/2026/nla/index.html)
verbalize activations directly instead of enumerating features; and
[sparse crosscoders](https://arxiv.org/abs/2603.05805) diff features *across models*
(MoE vs dense), the cross-layer/cross-model answer to single-site SAEs. For the
vault: any claim section 18/24 makes from a fingerprint inherits the telescope caveat
— features the SAE missed are invisible to the fingerprint, and "reconstruction is
good" does not mean "coverage is complete."

## Applications, ranked

**A1 — The missing genre: one note through the whole system.** A candidate new
section: pick one real note (this video's own note is the natural choice) and trace
it end-to-end — raw text → Qwen 1024-dim vector rendered 32×32 → where it lands on
the map/planet → SAE fingerprint rendered 128×128 (sparsity as darkness) → its named
top features → its retrieval neighbors at each pipeline stage. Every panel is the
same note; the reshape is drawn, not assumed (T1+T2+T3 in one figure series). This
was the single most-proposed extension across all 34 sections.

**A2 — `vector_image()` as a house primitive in `scripts/plot_assets.py`.** One
helper: reshape 1024-dim → 32×32 and 16,384-dim → 128×128, `saturated_magma` +
`punch` per house rule, side length and normalization stated in the meta line,
optional ink-style annotation of named dimensions (the T1 "annotated print" move —
mark the cone dimensions on the mean-vector image, mark latent 977 on a fingerprint).
Sections 16, 17, 18, 20, 22, 25, 28 all proposed exactly this rendering; one
primitive serves them all and keeps the series indistinguishable in palette.

**A3 — A retrieval logit lens.** The search pipeline has stages (query embedding →
candidate over-fetch → freeze filter → rank); apply the final readout (top-5 notes)
at every stage and show where the answer crystallizes — including the honest caveat
that early stages changing without the top-5 flipping still means work is happening.
Doubles as a debugging instrument for the eval gate (#85): a regression could be
localized to the stage where the crystallization point moves.

**A4 — Steering with a stated dynamic range.** Sections 18/21/24 name latents by
exemplars — correlation. The video's move is causal with calibration: clamp latent
977 ("EpicMap") or feature 8684 ("technical jargon") off/moderate/absurd, show
retrieval before/after each, and state the observed-maximum the clamp is relative to.
A latent that survives this earns its name; readers proposed it independently for
sections 18, 20, 21, and 24.

**A5 — Similarity matrices as first-class images, seriated on camera.** Section 12's
Gram matrix already proved reordering reveals blocks. Extend to section 19: six
metrics as six 568×568 images side by side — metric disagreement becomes texture
divergence the eye catches before any bar chart (T1 applied to populations).

**Cheap immediate fixes (T5 hygiene flagged by readers):** section 19's support axis
auto-scale inflates the 48% hub cut — pin to data limits; section 20's bridge band
(0.556–0.631) likewise; section 12's three spheres are resized to fit — redraw at
constant radius so the 11× mean vector visibly crashes out of the sphere; sections
26/28's share changes read better as scaled areas than bar heights.

**Not adopted:** the wooden-desk skeuomorphism and camera moves are video devices —
manim clips could do the reshape-then-annotate beat, but the stills should stay in
house anatomy. Categorical color-as-identity is available but must not touch the
`DIM`/`RED` conventions.

## What this changes about how figures get made

The house style already wins on honesty (nulls, verdicts, walls). What Welch adds is
**individuation**: before reaching for a distribution, ask "can I show this happening
to one real note, with the vector itself on screen?" The record's strongest future
figures are probably pairs — the individual trace (his grammar) sitting next to the
population null (ours), same axis, same palette.
