# Grounded profile regeneration

`ytk profile` treats the profile as an auditable, scored artifact.

Themes are concrete, full-history categories: clustering depends only on
corpus size and embedding geometry, never on timestamp coverage, so a category
whose notes lack capture times keeps its place in the taxonomy. Freshness is
reported per theme as an overlay (`fresh-notes` in the rendered XML), not used
to merge or erase dimensions.

Each portrait claim is an observation attached to its most relevant theme and
declares a `kind` calibrated to the capture-signal ladder: `recurrence` (any
evidence), `engagement` (needs at least one r>=1 deliberate save), `intent`
(needs at least one r>=2 authored thought), and `project` (needs at least one
r>=3 authored directive). Knowledge, expertise, and identity are not
expressible kinds, so passively ingested content can never ground a claim
about the person rather than the captured material.

## Evidence contract

Every structured portrait claim and every theme summary carries one to four
exact vault item ids. Assembly rejects missing ids, theme evidence outside its
cluster, claims attached to unknown clusters, claims whose evidence does not
reach their kind's signal floor, and claim evidence sets whose newest known
capture time is older than `interest.decay_half_life_days` (90 days by
default). Unknown legacy capture times cannot establish claim freshness, but
they never invalidate a theme summary: theme descriptions are full-history and
freshness-exempt.

The rendered XML includes those refs plus an evidence catalog with capture
times. Audit it independently with:

```bash
uv run scripts/check_profile_grounding.py
```

## Annotation-free ranking score

Each full regeneration evaluates the actual short profile claims in the pinned
SigLIP text/image space. Recent, visually indexed vault saves are
positives; matched discovery-queue items not yet written to the vault are
comparison candidates. Matching prefers the same source, then uses the nearest
pending visual neighbors as hard cross-source fallbacks when that source has no
pending pool. Claims that cite a selected positive are removed from
the evaluation query so evidence ids cannot trivially reveal the answer. A
written thought increases a save's signal weight but is not required: capture
into the vault is the positive action being evaluated.

The score is multi-positive nDCG under protocol
`bump-forward-evidence-redacted-visual-v1`. The candidate ids, their
fingerprint, encoder revision, query-claim count, score, and comparison delta
are persisted in the interest snapshot. The previous candidate cohort is
reused while all of its items remain available; only that fixed-cohort,
fixed-encoder case is called comparable. A decrease larger than
`interest.profile_eval_regression_tolerance` (0.02 by default) prints a warning.

Pending candidates are an operational single-user proxy for non-saves, not
explicit dislikes. Evidence redaction prevents direct citation leakage, but the
profile generator still observes the full history; the protocol name records
that limitation rather than claiming a fully history-held-out BUMP evaluation.
