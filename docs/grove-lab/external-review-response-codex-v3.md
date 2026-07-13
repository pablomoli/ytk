# Codex external review response: grove E7 implementation audit

```json
{
  "verdict": {
    "implementation": "diverges",
    "amendments": {
      "A1": "reject",
      "A2": "approve",
      "A3": "approve"
    },
    "clear_to_run": false,
    "summary": "The control generator is broadly faithful, but the served manifest leaks truth through semantic stimulus IDs and the randomized order lets topology-invariance and identification trials expose true trees before semantic readback. The UI can also lose or duplicate responses and does not measure RT from completed stimulus presentation. Blocking findings: H1, H2, H3, H4."
  },
  "findings": [
    {
      "id": "H1",
      "severity": "critical",
      "target": "endpoint",
      "argument": "Removing each trial's answer field does not isolate truth because stimulus IDs encode roles such as true, ctrl, rerender, and anchor. The browser receives those IDs in both the stimulus table and trial references, so correctness is recoverable from the network response or client state without opening the private manifest.",
      "evidence_or_repro": "scripts/grove_lab/e7_manifest.py:190-211 creates role-bearing IDs; ytk/ui/server.py:600-604 strips only the answer field and returns all IDs unchanged.",
      "required_change": "Generate opaque public stimulus IDs with no bucket, task, trial, or role information. Store answers and the opaque-to-private mapping in a separate private answer-key file. Serve a separately hashed public manifest and add a test asserting that its serialized form contains none of: true, ctrl, rerender, anchor, or answer.",
      "confidence": 1.0
    },
    {
      "id": "H2",
      "severity": "critical",
      "target": "manifest",
      "argument": "All scored tasks are shuffled together despite the preregistration saying exploratory identification runs last. A topology-invariance trial explicitly displays a true topology as anchor and rerender; if it occurs before semantic readback for that bucket, it teaches the repeated true structure. An isolated identification trial can likewise expose it early. This contaminates the primary construct before it is measured.",
      "evidence_or_repro": "scripts/grove_lab/e7_manifest.py:215-232 places Tasks 1-3 in one main list and applies one unrestricted permutation. docs/grove-lab/e7-preregistration.md states that 3-AFC identification runs last.",
      "required_change": "Regenerate in blocks: practice; first Task-1 exposure for each bucket in randomized bucket order; remaining Task-1 repetitions; Task 2; then exploratory Task 3. Randomize within blocks and balance left/right there. Mark only each bucket's first Task-1 exposure as the uncontaminated primary observation; repetitions are learning-sensitive secondary observations.",
      "confidence": 1.0
    },
    {
      "id": "H3",
      "severity": "critical",
      "target": "trial-ui",
      "argument": "Response persistence is unsafe for an irreversible run. The UI advances in finally even when POST fails, has no submission lock, and provides no resume mechanism. A failed request loses a trial; rapid confidence clicks can append duplicates and advance multiple indices; refreshing restarts at trial zero. The server accepts duplicates, unknown trials, invalid choices, and unrestricted confidence/RT values.",
      "evidence_or_repro": "web/src/routes/grove.tsx:180-185 advances regardless of HTTP result and lines 224-229 leave every confidence button active; ytk/ui/server.py:586-616 performs no manifest validation or duplicate protection.",
      "required_change": "Disable all response controls immediately on submit; advance only after an ok response; show a retry state on failure. Make POST idempotent by manifest hash plus trial ID, validate the trial and allowed choice, constrain confidence to 1-5 and RT to a nonnegative range, and reject conflicting duplicates. On load, resume from server-confirmed completed trials. Add tests for failure, retry, double submission, invalid choice, and refresh/resume.",
      "confidence": 0.99
    },
    {
      "id": "H4",
      "severity": "major",
      "target": "trial-ui",
      "argument": "RT is not measured from stimulus mount as claimed. For trial zero the timer begins before the manifest fetch completes because the index effect runs on initial component mount. On later trials it begins before dynamic import, WebGL setup, data planting, and the 0.8-second growth animation finish. Choice buttons are immediately available, so RT mixes loading/rendering time with decision time and stimuli can be judged before fully grown.",
      "evidence_or_repro": "web/src/routes/grove.tsx:161-170 starts the index timer independently of manifest/stimulus readiness; lines 133-148 mount asynchronously; lines 179 and 201-220 permit choice without a ready gate.",
      "required_change": "Have each StimulusCanvas report readiness after scene creation and data planting, wait for every canvas in the trial plus the fixed growth interval, then reveal or enable choices and start RT. Reset readiness per trial and test that trial zero cannot start timing during manifest loading.",
      "confidence": 0.99
    },
    {
      "id": "H5",
      "severity": "major",
      "target": "protocol",
      "argument": "A1 is not implemented as described. Changing render_seed does not rotate the camera; it changes branch wandering, fork perturbations, root decoration, leaf placement, and other stochastic geometry while the camera remains fixed. Random render variation is useful for Task 2, but it is not camera-azimuth randomization and introduces additional nuisance variation into Task 1.",
      "evidence_or_repro": "web/src/routes/grove.tsx:140-144 passes render_seed as GroveParams.seed. web/src/lib/grove/scene.ts:174 initializes the geometry RNG from that seed while the camera is fixed at scene.ts:133-136; web/src/lib/grove/datatree.ts:43-96 consumes the RNG for limb geometry.",
      "required_change": "Separate geometry_seed from camera_azimuth. For Task 1, use matched geometry-seed policy across true/control pairs and independently rotate the camera around the vertical axis. For Task 2, retain distinct geometry seeds because rerender invariance is the construct, but also record an explicit camera azimuth. Amend the manifest language accordingly.",
      "confidence": 1.0
    },
    {
      "id": "H6",
      "severity": "major",
      "target": "protocol",
      "argument": "Task-1 repetitions reuse one exact true topology, so later trials are not additional independent semantic reads. Once the subject infers a recurring silhouette, subsequent answers can be based on recognition, including recognition of an initially incorrect choice. Early-versus-late reporting reveals learning but does not restore the intended naive measurement.",
      "evidence_or_repro": "scripts/grove_lab/e7_manifest.py:185-200 inserts the same true_nodes three times per bucket while only controls and render seeds change.",
      "required_change": "Designate the first Task-1 presentation per bucket as primary and the other two as secondary learning/consistency trials. Present all three buckets' primary trials before any repeat or Task-2 exposure. Do not use the aggregate 7/9 band as the sole claim about naive semantic legibility.",
      "confidence": 0.98
    },
    {
      "id": "H7",
      "severity": "minor",
      "target": "manifest",
      "argument": "The generator claims balanced early/late ordering but implements an unrestricted permutation with no balancing check. The actual manifest may therefore concentrate a task or bucket in one portion of the session.",
      "evidence_or_repro": "scripts/grove_lab/e7_manifest.py:227-232; the comment promises alternating balanced block draw, but the code calls rng.permutation over the complete main list.",
      "required_change": "Implement explicit stratified block construction and add tests for task order, first-exposure constraints, bucket coverage, left/right balance, and early/late distribution.",
      "confidence": 1.0
    },
    {
      "id": "H8",
      "severity": "minor",
      "target": "manifest",
      "argument": "A2 is a reasonable fallback, but for visual-craft it tests payload placement on a fixed wire skeleton rather than adjacency topology. A correct result would support legibility of mass/persistence placement, not semantic legibility of branching structure.",
      "evidence_or_repro": "scripts/grove_lab/e7_manifest.py:78-129 permits a successful control when only payloads move; the handoff states visual-craft parent reassignment is identity-locked.",
      "required_change": "Keep the visual-craft trials, but preregister their interpretation separately as payload-geometry readback. Do not pool them unqualified with buckets whose controls alter adjacency, and treat their Task-1 result as exploratory if the control's parent map is unchanged.",
      "confidence": 0.96
    }
  ],
  "answers": {
    "q1": "Subject cooperation is acceptable for a personal case study, but the trial client should still follow ordinary blinding hygiene. Split the private answer key from the public manifest and use opaque public IDs; currently the endpoint itself reveals stimulus roles despite stripping answer.",
    "q2": "Early-versus-late reporting is not enough. Make the first Task-1 exposure per bucket the primary naive observation, place all three first exposures before repeats or other scored tasks, and treat trials 2-3 as secondary learning/consistency data.",
    "q3": "A six-node tree is winnable in principle if mass and persistence placement visibly alter limb length and girth, but it cannot test adjacency topology when the skeleton is unchanged. Keep visual-craft as an explicitly payload-legibility or exploratory condition rather than interpreting it identically to epicmap and ai-building.",
    "q4": "The largest truth leak is semantic stimulus IDs in the served manifest. Additional implementation defects are cross-task ordering contamination, response loss through finally, duplicate-submit risk, restart-on-refresh, lack of server validation/idempotency, premature choice availability, and RT beginning before stimuli are ready. No evidence of a deliberate left/right layout or color leak was found; single-tree rendering does normalize scale and uses the same first-bucket tint.",
    "q5": "The duration is acceptable, but use explicit blocks and offer a pause after Task 1, with safe server-backed resume. Pausing after the primary semantic block also reduces fatigue without allowing later tasks to contaminate it."
  }
}
```
