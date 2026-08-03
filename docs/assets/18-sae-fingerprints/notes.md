# SAE feature fingerprints — working notes

Pre-registered predictions: `preregistration.md` (commit ea2315b, before any
measurement). Landscape and API facts: `landscape.md`. This file records
results in experiment order, including failed predictions, verbatim against
what was registered.

## 18.0 — API smoke test (2026-08-02)

**Instrument findings first.** `POST /api/search-all` returns HTTP 500 —
not a validation message — when `sortIndexes` is omitted; the field is
required in practice. With the full body the endpoint works anonymously.
Measured latency ~8s per call for a 1546-char note (the number the
landscape flagged as unpublished): 568 notes ≈ 75 min sequential via API,
which strengthens the local-rig plan for the batch. Raw request/response
JSON in `smoke/`.

**Pre-registered prediction: FAILED as operationalized.** Registered: ">= 6
of the top 10 features have names recognizably related to the note's
content"; kill at < 3. Note: the De-Slop codebase video. Result under the
naive operationalization (top-10 by `maxValue`, the API's own ordering):
**1 of 10** — nine are token-level spike features ("forms of the verb
walk", "references to the name John", "repetition of the word every").
Below the kill threshold as written.

**Diagnosis before invoking the kill.** Sorting by peak single-token
activation structurally selects features that spike once on one token.
Re-ranking the same response by summed activation across tokens (recorded
as an instrument amendment, not a prediction edit): **3 of 10** topical —
"technical jargon and programming-related terms" (#8684) becomes rank 1
with 41 of ~350 tokens active, plus "deep learning" (#6906) and "skills or
skill sets" (#11299) — but function-word features ("a", "the",
punctuation, "to") hold ranks 2-5 because they are dense in all English
text. 3/10 sits exactly at the kill boundary and still under the
registered 6/10.

**What was learned (not assumed).** A single note cannot rank its own
features: without each feature's corpus-wide baseline frequency there is
no way to separate content features from generic-English scaffolding —
the same correction tf-idf applies to words, and the same operation
18.4's tag diffing was already designed to do. Two consequences carried
forward:

1. Fingerprints aggregate by **sum over tokens** (peak-token ranking is
   structurally misleading); the mean-vs-max question from prior art is
   answered for ranking purposes before the batch ran.
2. All feature *reading* happens on baseline-corrected scores
   (note-vs-corpus or tag-vs-corpus differentials), never on raw
   single-note rankings. Step 18.3's cone candidates are, by this same
   logic, expected to be exactly the scaffolding features that polluted
   this list — the smoke test previewed the cone rather than refuting the
   pilot.

**Verdict:** not a kill (>= 3 under the amended instrument), but the 6/10
prediction failed and is reported as failed. The pilot proceeds with the
two instrument rules above; if baseline-corrected reading in 18.3/18.4
still surfaces garbage, that is the real kill.

## 18.1 — local rig cross-validation (2026-08-02)

**Prediction: CONFIRMED, with one instrument correction en route.** The
first scoring pass compared local top-10-by-sum over all 16k features
against the API's top-10 — but the API only returns its top-100 features
by peak activation, so the two sides ranked over different candidate
pools. Unrestricted overlap (2.0/10 mean) exactly equals the count of
local winners present in the API pool at all, and median relative
activation difference on shared features was already ~2% — values agreed,
pools did not. Pool-matched scoring (rank both sides inside the API's
candidate set): **10/10 on all five notes, mean relative activation
difference 0.4-2.3%**, against the registered >= 7/10 and <= 10%.

The rig — unsloth-mirror Gemma 2 2B bf16 on CPU, hook
`blocks.20.hook_resid_post`, SAE `gemma-scope-2b-pt-res /
layer_20/width_16k/average_l0_71` — is validated as an instrument. The
mirror-vs-official weight question is closed by the same numbers.

Carried forward:

1. **The API's 100-feature cap is a real ceiling**, not a nuisance: most
   of a note's high-mass (dense) features fall outside its top-100 by
   peak. Corpus statistics computed from API responses would be silently
   truncated — the batch must be local. (`rig-validation.json` keeps both
   overlap numbers.)
2. **Measured throughput: 25-43s/note on CPU** (~330-530 tokens each),
   so the full batch is ~4.5 CPU-hours. An MPS run is only admissible if
   it passes this same validation procedure against the now-trusted CPU
   reference.

## Next

18.2 batch (device: CPU, or MPS if it passes the same validation), then
18.3 cone naming.
