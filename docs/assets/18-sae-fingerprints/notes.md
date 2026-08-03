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

## 18.2 — the batch, and the two-store incident (2026-08-03)

MPS passed its admissibility gate 10/10 against the CPU reference, then the
first full batch silently ran against a stale database: `runtime_config()`
picks the live HTTP server only when CHROMA_URL is set, and that env var is
an import side effect of `ytk.vault` — a bare `from ytk import store`
opens the embedded legacy fork (videos_v2 = 200 vs 289 live) with no
error. Caught because 127 notes had no text and the number refused to make
sense; filed as #164 (mechanism fix in store.py, gate-gated). The batch
was re-run in full against the live store: **568/568 fingerprinted, 0
skipped, 0 zero-fingerprints**, 93 min on MPS, per-row text sha256 now in
the manifest so store drift is diffable instead of forensic.

The registered acceptance check ("mean per-note L0 within 2x of 71") was
itself misspecified: 71 is the SAE's per-token L0; the union of features
across a 300-500-token note is a different quantity (measured mean 5209).
Reported as a miswritten check, not waved through.

## 18.3 — the cone, named (2026-08-03)

**Prediction: CONFIRMED — after the presence notion earned its third
instrument lesson.** Under union presence (any activation on any token),
953 features exceed 90% document frequency: a third of the dictionary
ticks somewhere in every note, so ubiquity is an artifact. Under mass
presence (note's top-256 features by summed activation), the curve
separates cleanly: **31 features above 90% df, 56 above 70%** — against
the registered >= 5, with the kill floor (nothing above 70%) nowhere in
sight.

The heaviest cone features read as register and domain, exactly as
predicted: programming jargon (#8684), programming/code structure (#549),
programming keywords and parameters (#10931), scientific/technical
process vocabulary (#6143), proper nouns (#6631, the single heaviest —
titles and names), sentence-position scaffolding (#15509), document-start
markers (#5052). The Qwen cone's likely composition — technical register
+ explanatory prose + name-dense summaries — now has named, checkable
constituents.

**Auto-names are hypotheses, not ground truth — measured twice.** #4932
("drug usage and its effects", df 1.0 under union) fires on ' session',
' repo', ' mode', ' skill' in a coding note; #12763 ("privilege and
social identity", cone rank 2) fires on subword fragments ('cock' from
cockpit, 'offs' from trade-offs) and glue tokens. Rule carried into
18.4/18.5: read differential feature *sets*; never conclude from a single
auto-name, and probe any load-bearing feature at token level via
`/api/activation/new` before quoting it.

## Next

18.4 tag regions as differential feature sets (with tag-shuffle control),
then 18.5 roads as feature diffs. Both read fingerprints.npz; both apply
the mass-presence and set-not-name rules above.
