# External review handoff v3: E7 implementation audit before the run

Same contract as rounds 1-2 (`external-review-handoff.md`,
`external-review-handoff-v2.md`, your responses alongside). This round is
small and surgical: the E7 preregistration you rated run-with-changes has
been implemented. Audit the implementation against the protocol BEFORE the
subject runs it — after exposure, defects are unfixable. Repo access
assumed; tests: `uv run --extra dev pytest tests/ -q`.

## What was built since your v2 response

Your required metric fixes landed first (context, already re-measured,
artifact `shootout-v3.json`): symmetric/injective/tie-skipping triplet
gate — signal survives (agglo 0.60/0.75/0.74); BOTH your correspondence
null and structure null sit at the 0.33 chance floor; HDBSCAN's
single-linkage tree passes the identical gate (0.59/0.74/0.65), so the
agglo choice is now recorded as a product decision. Claims narrowed to
ordinal branching order per G2/G8.

E7 machinery (this round's audit target):

- `scripts/grove_lab/e7_manifest.py` — manifest generator.
  `shuffle_topology` (tested, `tests/test_grove_e7.py`) implements the
  constrained control; `build_manifest` assembles 2 practice + 9 task-1 +
  9 task-2 + 6 exploratory trials, 55 stimuli, seeded order, sha256 over
  canonical JSON, refuses overwrite without `--force`.
- `ytk/ui/server.py` — `GET /api/grove/e7` serves the manifest with every
  per-trial `answer` stripped (tested: zero leaks); `POST
  /api/grove/e7/response` appends {trial, choice, confidence, rt_ms, ts}
  to `~/.ytk/grove/e7-responses.jsonl`, never echoes correctness.
- `web/src/routes/grove.tsx` `ReadbackPage` (behind `?readback=1`) —
  trial runner: pair layout for tasks 1-2 (anchor above for task 2),
  single tree + 3 name buttons for exploratory, confidence 1-5 after
  every choice, RT measured from stimulus mount, no feedback, no back
  navigation. Verified live on the practice trial only (synthetic trees;
  contamination rule respected — no scored stimulus has been rendered
  anywhere the subject or the authors' chat can see).

## Amendments made pre-exposure (approve or reject each)

A1. Camera azimuth randomization via per-stimulus render seeds (isotropic
    fork azimuths make an independent render seed equivalent to a camera
    rotation; no scene change).
A2. Second control move — (mass, persistence) payload permutation within
    depth levels — added because within-level parent permutation is
    identity-locked on visual-craft's topology (root -> 3 limbs -> both
    sub-branches under one limb). Preserves every preregistered stratum
    exactly; breaks joint mass-by-position. Question for you: is a
    payload-permuted control WEAKER than a reattachment control for the
    semantic-readback construct (the subject may notice identical wire
    skeletons)? If so, should task-1 trials for small topologies be
    demoted to exploratory, or is the payload move sufficient?
A3. Response log at `~/.ytk/grove/e7-responses.jsonl` (hub cannot write
    into the repo), archived to `docs/grove-lab/` post-run.

## Specific audit questions

1. **Truth isolation.** The manifest file on disk contains `answer`
   per trial; the endpoint strips it. The subject could open the file or
   the endpoint code. We rely on subject cooperation (he owns the
   machine). Is that acceptable for a single-owner case study, or should
   answers be split into a separate file the trial UI never touches?
2. **Stimulus dependence.** Task-1 trials reuse the SAME true topology
   three times per bucket (different controls, different render seeds).
   The subject may recognize the true tree across trials and lock in
   (right or wrong) — a learning confound inside a bucket. Should trial 2
   and 3 for a bucket be demoted to secondary, or is early-vs-late
   reporting enough?
3. **Small-topology power.** visual-craft has 6 nodes; after A2 its
   controls differ only in payload placement. epicmap has 15 nodes,
   ai-building 13. Is task 1 winnable-in-principle for a 6-node tree, or
   should visual-craft be exploratory-only?
4. **Anything in the trial runner that leaks correctness** (ordering,
   layout, timing, network behavior)? `ReadbackPage` is ~100 lines;
   please read it adversarially.
5. Trial counts: 9+9+6 at roughly 30-60s each is a 15-25 minute session.
   Acceptable for one sitting, or split into blocks with the manifest
   marking a pause point?

## Output format

ONE fenced JSON block:

```json
{
  "verdict": {
    "implementation": "faithful | faithful-with-fixes | diverges",
    "amendments": {"A1": "approve|reject", "A2": "approve|reject", "A3": "approve|reject"},
    "clear_to_run": true,
    "summary": "<= 3 sentences"
  },
  "findings": [
    {"id": "H1", "severity": "critical | major | minor",
     "target": "manifest | endpoint | trial-ui | protocol | 'new'",
     "argument": "...", "evidence_or_repro": "file:line or repro",
     "required_change": "...", "confidence": 0.0}
  ],
  "answers": {"q1": "...", "q2": "...", "q3": "...", "q4": "...", "q5": "..."}
}
```

If `clear_to_run` is false, list the blocking finding ids. Fixes will be
applied and, if they touch stimuli, the manifest regenerates with a new
seed before the run.
