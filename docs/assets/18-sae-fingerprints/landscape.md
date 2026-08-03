---
generated: 2026-08-02
generator: gemmascope-landscape workflow (6 agents: 4 research fronts, 1 verify, 1 synthesis)
verification: 14/14 load-bearing claims CONFIRMED against primary sources
---

# SAE Feature Fingerprints for ytk — Research Report

Scope: computing sparse-autoencoder feature fingerprints for 568 vault notes (~100-300 tokens each, thesis+summary) so that (a) the shared cone direction can be read as named features, (b) tag regions can be checked against feature sets, and (c) interpolation paths become named-feature diffs. State of the field as of August 2026.

---

## 1. Landscape

Five suites matter; one is the clear default.

**Gemma Scope (original)** — DeepMind, Aug 2024 ([arXiv:2408.05147](https://arxiv.org/abs/2408.05147), weights at [google/gemma-scope](https://huggingface.co/google/gemma-scope)). Covers Gemma 2 2B and 9B on every layer and sublayer (attention output, MLP output, post-MLP residual), plus select layers of 27B. Over 400 JumpReLU SAEs, >30M features, widths 2^14 to 2^20, CC-BY-4.0. Verified against the HF page, including the license and the all-layer coverage. Roughly two years of ecosystem maturity: SAELens integration, full Neuronpedia dashboards with auto-generated names for essentially every 16k/131k feature, and a large published-paper base.

**Gemma Scope 2** — DeepMind, technical paper dated 2025-09-16, public release 2025-12-19 ([technical paper PDF](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/gemma-scope-2-helping-the-ai-safety-community-deepen-understanding-of-complex-language-model-behavior/Gemma_Scope_2_Technical_Paper.pdf), weights at [google/gemma-scope-2](https://huggingface.co/google/gemma-scope-2)). Verified to exist and to cover all Gemma 3 sizes (270M, 1B, 4B, 12B, 27B), PT and IT, all layers, three sites per layer, plus crosscoders and cross-layer transcoders. Select-layer sweep indices verified against Table 1: 270M {5,9,12,15}, 1B {7,13,17,22}, 4B {9,17,22,29}, 12B {12,24,31,41}, 27B {16,31,40,53}, zero-indexed. Select-layer widths {16k, 64k, 256k, 1m} at L0 targets {10, 50, 150}; only residual-stream SAEs get 1m. IT SAEs are finetuned from PT SAEs on rollout data, not trained from scratch. CC-BY-4.0.

**Llama Scope** — OpenMOSS/Fudan, Oct 2024 ([arXiv:2410.20526](https://arxiv.org/abs/2410.20526), weights at [fnlp/Llama-Scope](https://huggingface.co/fnlp/Llama-Scope)). Verified: 256 TopK SAEs across all layers and 4 positions of Llama-3.1-8B-Base only, widths 32k/128k, Apache 2.0. The attention-position SAEs are explicitly marked "(Not recommended)" on the HF page for dead features; use residual or MLP positions.

**Goodfire AI** — single-layer SAEs for [Llama 3.1 8B Instruct (layer 19)](https://huggingface.co/Goodfire/Llama-3.1-8B-Instruct-SAE-l19) and [Llama 3.3 70B Instruct (layer 50)](https://huggingface.co/Goodfire/Llama-3.3-70B-Instruct-SAE-l50), Jan 2025. Not a full suite, and licensing is gated by Meta's Llama Community License. Unverified beyond secondary coverage.

**EleutherAI [sparsify](https://github.com/EleutherAI/sparsify)** — a training toolkit, not a packaged suite. Relevant only if ytk ever trains its own SAE (e.g., directly on the Qwen3 embedding space — see prior art, section 4). OpenAI's [GPT-2 small SAEs](https://cdn.openai.com/papers/sparse-autoencoders.pdf) are historically important but not a serious 2026 option.

**Recommended default: Gemma Scope original, Gemma 2 2B PT, residual stream, layer 20, width 16k, average L0 71.** This exact configuration is verified as the Neuronpedia flagship demo — the [google/gemma-scope](https://huggingface.co/google/gemma-scope) README has a literal section "Which SAE is in the Neuronpedia demo?" pointing to `gemma-scope-2b-pt-res/layer_20/width_16k/average_l0_71`. It is the only configuration where every one of the 16k features already has a human-readable Neuronpedia name — which is the entire point for ytk, since goals (a)-(c) are about *reading* features, not just computing them. Gemma Scope 2 (Gemma 3 1B layer 13 or 4B layer 17, 16k/64k) is the secondary option, but whether Neuronpedia has auto-interp names for its features yet is unverified, and without names the fingerprints are just anonymous sparse vectors. Note the naming trap: "gemma-scope-2b" (Gemma Scope for the 2B Gemma 2 model) is not "gemma-scope-2" (the Gemma 3 suite).

---

## 2. API cheat sheet — Neuronpedia

Base host: `https://www.neuronpedia.org/api/*` (verified from the [NLA demo notebook](https://github.com/hijohnnylin/neuronpedia/blob/main/apps/nla/api_demo.ipynb) and route sources). Docs at [docs.neuronpedia.org/api](https://docs.neuronpedia.org/api), which states verbatim that the API "is a work-in-progress." Ground truth below comes from the open-source route sources at [hijohnnylin/neuronpedia](https://github.com/hijohnnylin/neuronpedia), independently verified.

### VERIFIED (route source read and confirmed)

**Fingerprint a text — `POST /api/search-all`.** The endpoint for "which features fire on this text," and the one that matches the ytk use case. Verified body: `{modelId, sourceSet, text: string | string[], selectedLayers: string[] ([] = all SAEs in set), sortIndexes?: number[], ignoreBos: true, densityThreshold: -1, numResults: 50 (max 100)}`. Batch mode is native: pass an array of texts and the response is `{results: [{tokens, result[], counts, sortIndexes}]}`, one object per input text. Correction applied: each result item's `index` is a **string**, not a number. Swagger says verbatim: "Contact us to increase your rate limit for free if you hit it."

```bash
curl -s https://www.neuronpedia.org/api/search-all \
  -H 'Content-Type: application/json' \
  -d '{"modelId":"gemma-2-2b","sourceSet":"gemmascope-res-16k",
       "selectedLayers":["20-gemmascope-res-16k"],
       "text":["<note thesis+summary>"],"numResults":100}'
```

**Feature name/explanation — `GET /api/feature/{modelId}/{layer}/{index}`.** No auth for public models; returns the full feature record including explanations and top activations. Browser-usable:

```
https://www.neuronpedia.org/api/feature/gemma-2-2b/20-gemmascope-res-16k/12082
```

**Batch feature metadata — `POST /api/features`.** Array of `{modelId, layer, index, maxActsToReturn?}`, one round trip for many features — this is how the cone's top-k features get their names in one call. Two verified implementation nuances: only the **first** element's `maxActsToReturn` is honored for the whole batch, and the response re-sort keys on `index` alone, so keep batches within a single SAE (one layer) to guarantee order.

**Single-feature activation test — `POST /api/activation/new`.** Body `{feature: {modelId, source, index}, customText: string | string[]}`; returns per-token `values[]`, `maxValue`, `maxValueIndex`, DFA fields. Nuance: swagger types `index` as a string. Useful for the roads test — probe one named feature along a path of texts.

**Explanation semantic search — `POST /api/explanation/search`** (body `{modelId, layers: [...], query (min 3 chars), offset?}`, swagger defaults are literally `gemma-2-2b` + `['20-gemmascope-res-16k', ...]`) and **`POST /api/explanation/search-all`** (query only, all of Neuronpedia). Both paginate at 20 results per page with `hasMore`/`nextOffset`. This is the reverse index: "is there a feature about X" → feature id.

**Auth and rate limits.** Header is `x-api-key`; a free key lives on the account page; anonymous access works for all endpoints above (all are `withOptionalUser`). Rate limiting is per **source IP**, 60-minute sliding window: `search-all` 1600/hr, `activation/new` 1000/hr, `explanation/search` 200/hr, `steer` 120/hr. A key raises limits only if the specific key string is on an admin allowlist (`HIGHER_LIMIT_API_TOKENS`), and — correction — the higher tier does **not** raise `search-all` (1600 in both tiers). 568 notes fits in one hourly window with room to spare, even one request per note. Whether the limiter is actually enabled in production (`ENABLE_RATE_LIMITER`) is unverifiable from outside; plan as if it is on.

**Bulk data is S3, not API.** The old `GET /api/explanation/export` route is verified dead — it returns HTTP 400 with a JSON body pointing to the [S3 dataset bucket](https://neuronpedia-datasets.s3.us-east-1.amazonaws.com/index.html?prefix=v1/). For anything missing, the maintainers document a 48-hour custom-export turnaround (support@neuronpedia.org). Downloading the full explanation catalog for `gemma-2-2b/20-gemmascope-res-16k` once, up front, is cheaper than 16k feature GETs.

### UNVERIFIED

- Per-request latency of `/api/search-all` — no published numbers. This, not rate limits, decides whether 568 notes takes minutes or hours via API.
- The exact `sourceSet`/`selectedLayers` strings above match the swagger defaults for the explanation-search route, but the search-all values for Gemma Scope were not round-tripped against the live server.
- The S3 v1/ dump file format (parquet vs jsonl, exact schema) — existence confirmed, contents not listed.
- Whether account signup still auto-provisions a key with no extra gating.
- The steering endpoints (`/api/steer`, `/api/steer-chat`) work per docs, but the docs' supported-model list is likely stale. Not needed for the pilot.

---

## 3. Local pipeline

**Stack:** `sae-lens` (now maintained under Decode Research, same org as Neuronpedia; v6.x, latest observed 6.46.1, Jul 2026) + PyTorch, Gemma 2 2B in bf16, `gemma-scope-2b-pt-res-canonical / layer_20/width_16k/canonical`.

**Run on CPU first, not MPS.** This is the load-bearing constraint and it is not about memory. [TransformerLens](https://github.com/TransformerLensOrg/TransformerLens) — which `HookedSAETransformer` subclasses — refuses to auto-select MPS and warns it "may produce silently incorrect results"; torch 2.8.0 has a known MPS `F.linear` bug on non-contiguous tensors, and at least one report claims related MPS bugs persist past 2.9. A blank error-free run that silently corrupts activations is the worst failure mode for a fingerprint corpus. The lower-risk MPS path, if speed demands it, is plain HF `transformers` + a forward hook on layer 20 feeding `sae.encode(...)` directly (SAELens's `SAE` is a plain `nn.Module` and works with any PyTorch activations) — but validate a handful of notes against CPU output before trusting it either way. Uncertainty flag: no Gemma-2-on-MPS bug is filed against plain transformers, but absence of a complaint is not a clean bill of health.

**Memory:** ~4.7 GB weights bf16, ~5.5-6 GB peak with the SAE (~150 MB for 16k width; computed from dimensions, not quoted). Fits on the M3/16GB, but per the machine's standing constraint: check `memory_pressure` first, close heavy tabs, and do not run the Chroma indexer or another model concurrently. The 4.7 GB figure is from a third-party aggregator, not an official spec — confirm at first load.

**Do not quantize.** A June 2026 paper ([arXiv:2606.03002](https://arxiv.org/html/2606.03002v2)) measured feature survival on exactly this class of setup (Gemma-2-2B, Gemma Scope 16k residual SAE): INT8 preserves 99% of features, but INT7 already degrades 19% and INT4 damages 55% — while *improving* perplexity, so perplexity checks would not catch it. The memory budget does not require quantization; skip the entire question by staying bf16.

**Throughput:** no direct M3 prefill benchmark exists for Gemma 2 2B. The 2-20 minute estimate for 568 notes is an unsourced extrapolation. Time 10 notes before planning anything around it.

**Minimal sketch** (hook-name caveat below):

```python
import torch
from sae_lens import SAE, HookedSAETransformer

device = "cpu"  # MPS only after a numeric spot-check against CPU
model = HookedSAETransformer.from_pretrained_no_processing("gemma-2-2b", device=device)
sae = SAE.from_pretrained(
    release="gemma-scope-2b-pt-res-canonical",
    sae_id="layer_20/width_16k/canonical",
    device=device,
)

tokens = model.to_tokens(note_text)  # thesis + summary, ~100-300 tokens
_, cache = model.run_with_cache_with_saes(tokens, saes=[sae])
acts = cache["blocks.20.hook_resid_post.hook_sae_acts_post"]  # [1, seq, 16384]

fingerprint_mean = acts.mean(dim=1).squeeze(0)   # keep both poolings; see section 4
fingerprint_max  = acts.max(dim=1).values.squeeze(0)
```

`from_pretrained_no_processing` is mandatory — [SAELens docs](https://decoderesearch.github.io/SAELens/dev/usage/) are explicit that SAEs are trained on raw activations and the default loader's folding would mismatch. The exact hook string `blocks.20.hook_resid_post.hook_sae_acts_post` is pattern-inferred from a documented `attn.hook_z` example, not confirmed verbatim for resid_post; verify against the installed version by printing `cache.keys()`.

**API vs local:** for the one-time 568-note batch, either works. Prefer **local** because the pilot needs iteration (pooling choices, BOS handling, thresholds — each re-run is free locally, a fresh 568-request pass via API) and because `search-all` caps at 100 features per text where local gives the full 16k vector. Prefer the **API** for feature *naming* (GET/POST feature endpoints, or the S3 explanation dump), for spot-validation of local numbers against Neuronpedia's reference inference, and if the local rig fights back — 568 texts is comfortably inside one rate-limit window.

---

## 4. Prior art

**The pipeline is validated, almost exactly.** "Interpretable Embeddings with Sparse Autoencoders: A Data Analysis Toolkit" ([arXiv:2512.10092](https://arxiv.org/abs/2512.10092), ICML 2026, [interp-embed.com](https://interp-embed.com)) — Nanda's group — runs documents through a reader LLM + pretrained SAE, max-pools token activations into one interpretable vector per document, and auto-labels dimensions from 10 activating vs 10 non-activating documents. It matches or beats dense embeddings on six retrieval benchmarks, wins specifically on property-based queries where dense embeddings get semantically fooled, and surfaces clustering structure (reasoning style, formatting) that dense embeddings miss. Note it uses **max-pooling**; the ytk sketch's mean-pooling is a divergence — compute both.

A parallel line decomposes dense-retrieval embeddings directly: Kang et al. ([arXiv:2411.00786](https://arxiv.org/abs/2411.00786)) show SAE latents over dense embeddings retain retrieval accuracy; CL-SR ([arXiv:2506.00041](https://arxiv.org/abs/2506.00041)) uses labeled SAE concepts as sparse indexing units; O'Neill et al. ([arXiv:2408.00657](https://arxiv.org/abs/2408.00657)) found "feature families" on 420k scientific abstracts. This matters for ytk because it means a *second* viable architecture exists — train a small SAE on the existing Qwen3 1024d vectors instead of running Gemma — though it forfeits Neuronpedia's pre-named features, which is why it is not the pilot.

**Test (a), naming the cone — predicted to work.** "The Geometry of Concepts" ([arXiv:2410.19750](https://arxiv.org/abs/2410.19750)) finds SAE feature space is measurably anisotropic — a dominant power-law-shaped structure, strongest at middle layers (layer 20 of 26 is late-middle) — and finds that analogical structure only becomes legible after projecting out global distractor directions. The shared cone should decompose into a small set of always-on features (likely register-level: technical English, explanatory prose, first-person summary) that Neuronpedia can name. "Sparse Autoencoders are Topic Models" ([arXiv:2511.16309](https://arxiv.org/abs/2511.16309), ICML 2026) supports reading fingerprints as theme-membership vectors and merging features post-hoc into named regions.

**Test (b), tag regions as feature sets — predicted to work.** This is exactly the toolkit paper's dataset-diffing task (which features distinguish corpus A from corpus B), run per tag against the corpus mean. Their result — larger, valid differences at 2-8x lower token cost than LLM-diffing — is the direct precedent.

**Test (c), roads as feature diffs — genuinely novel, with one warning.** No paper found does path interpolation between two documents' SAE vectors and narrates intermediates; existing work stops at pairwise diffing. And the warning is concrete: SAE feature directions do not obey word2vec arithmetic — antonym pairs show near-zero cosine similarity (0.001-0.042, [LessWrong: Empirical Insights into Feature Geometry](https://www.lesswrong.com/posts/rZmJwv4mSNeyeEu3g/empirical-insights-into-feature-geometry-in-sparse)), not negation. Prediction: a diff between two notes reads reliably as "features present in A, absent in B" (set difference), not as a semantic axis to walk. Frame roads as *fading-out set / fading-in set* rather than a traversed direction, and treat any midpoint interpolation as an experiment, not a given. This connects directly to the plane-geometry work in `docs/assets/15-plane-geometry/` — the interpolation figure there is the thing this would replace with named features.

---

## 5. The pilot, concretely

Next asset number is 18 (`docs/assets/18-sae-fingerprints/`). Steps ordered so each checkpoint kills the largest remaining risk. Reverse-chronological note order for the batch, per standing convention.

**Step 0 — API smoke test (30 min).** One note through `POST /api/search-all` (gemma-2-2b, layer 20 res-16k); fetch names for its top-10 features via `POST /api/features`. Confirms endpoint strings, response shapes, and that the features named for a real ytk note pass a sniff test. Artifact: raw request/response JSON + first observations in `docs/assets/18-sae-fingerprints/notes.md`. If the top features for a Go-tooling note are all garbage, stop and reconsider layer/width before building anything.

**Step 1 — local rig + cross-validation (2-3 h, mostly downloads).** `uv` env with sae-lens + torch, load model and SAE on CPU, verify the hook name from `cache.keys()`, run 5 notes locally and compare max-activating features against the API's output for the same texts. Time the 5 notes — this is the throughput measurement replacing the unsourced 2-20 min guess. Artifact: `results.json` with the local-vs-API feature-overlap table and measured sec/note.

**Step 2 — full batch (measured in step 1; likely under an hour wall-clock).** All 568 thesis+summary texts, BOS excluded, both mean- and max-pooled fingerprints saved as `float16` npz (568 x 16384 x 2 ≈ 37 MB) plus a note-id manifest. Check `memory_pressure` before launching. Artifact: the npz + a `01-fingerprint-stats.png` (per-note L0 distribution, feature-frequency rank plot — the corpus-primer style from `docs/assets/16-corpus-primer/`).

**Step 3 — name the cone (2 h).** Feature document-frequency across the corpus; features active in >90% of notes are the cone. Batch-fetch their names. Compare against the cone direction already measured in the plane-geometry work: project each candidate feature's decoder vector onto the known cone direction — do the named always-on features explain it? Artifact: `02-cone-features.png` (frequency vs mean activation, named) + a named-cone table in `notes.md`. This is deliverable (a).

**Step 4 — tag regions (2-3 h).** Per-tag mean fingerprint minus corpus mean (the toolkit paper's diffing, per tag); top-15 differential features per tag, named. Sanity metric: does the feature-set overlap between two tags track their embedding-space distance? Artifact: `03-tag-regions.png` (tags x top differential features heatmap — matplotlib checkpoint discipline applies; look at it before believing it). Deliverable (b).

**Step 5 — roads as diffs (2-3 h).** Take the note pairs used in the plane-geometry interpolation figure; compute fading-out / persistent / fading-in feature sets, named. Optionally probe 2-3 interesting features along the actual interpolated texts via `POST /api/activation/new`. Side-by-side: named-diff description vs the existing LLM narration of the same road. Artifact: `04-road-diffs.png` + verdict in `notes.md`. Deliverable (c), and the novel one — write down honestly whether set-diff reads better than narration.

Total: roughly two work sessions. Steps 3-5 are independent once step 2's npz exists.

---

## 6. Risks and unknowns

No claim checked by the verification pass came back WRONG — all 14 verdicts were CONFIRMED, several with corrections (already applied above: result `index` as string, `maxActsToReturn` first-element-only, re-sort by index alone, search-all not raised in the higher tier). The honest risk list is what was *not* verified:

**Correctness risks (could invalidate results silently):**
- MPS numerical correctness is unresolved beyond "TransformerLens warns against it." Even the plain-transformers path is unproven clean, and "torch >= 2.9" is necessary, not proven sufficient. Mitigation is baked into the pilot: CPU first, cross-check against Neuronpedia's inference in step 1.
- The hook string `blocks.20.hook_resid_post.hook_sae_acts_post` is pattern-inferred, not confirmed for resid_post in the current sae-lens release.
- Pooling choice is unsettled: the validated prior art max-pools; mean-pooling may wash out sparse features on 300-token texts. Both are computed in step 2 precisely because this is untested.
- The roads test rests on feature geometry that provably does not support word2vec-style arithmetic; if set-diffs also read poorly, (c) fails honestly — that outcome is informative, not wasted.

**Planning risks (could cost time, not truth):**
- Zero measured throughput numbers exist for this exact workload; every wall-clock figure above is a guess until step 1 times it. Same for the 4.7 GB memory figure (aggregator source).
- API latency for search-all is unpublished; `ENABLE_RATE_LIMITER`'s production state is unverifiable from outside.
- The exact `sourceSet` string for search-all against Gemma Scope was not round-tripped live; step 0 exists to catch this in 30 minutes.
- The S3 explanation-dump format was never inspected; if it is awkward, fall back to batched `POST /api/features` calls (fine at cone/tag scale, ~hundreds of features).

**Ecosystem unknowns:**
- Whether Neuronpedia has auto-interp names for Gemma Scope 2 features is unknown — this is the single fact that would change the model recommendation, and it was not confirmable. Until it is, Gemma 2 2B is the right choice for a naming-centric pilot despite being a 2024-generation model.
- Whether SAELens has Gemma Scope 2 loader support is likewise unchecked.
- Several cited papers ([2512.10092](https://arxiv.org/abs/2512.10092), [2511.16309](https://arxiv.org/abs/2511.16309), [2606.03002](https://arxiv.org/html/2606.03002v2), [2605.29507](https://arxiv.org/abs/2605.29507)) are ICML-2026-recent and were read at abstract depth via a summarizer, not full-text; their qualitative claims are consistent with each other but individual benchmark numbers should not be quoted onward without a full-text read. The 2600-range arXiv IDs were not independently resolved.
- No paper frames the exact "shared cone vs distinguishing features" split as a named technique — the anisotropy and diffing results are close proxies. The cone-naming framing in (a) is partially novel; a targeted follow-up search on "mean-centering SAE activations" could surface closer work if step 3's results look ambiguous.