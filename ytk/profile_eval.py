"""Annotation-free forward ranking evaluation for interest profiles (#94).

This adapts BUMP's profile-to-history direction to ytk's single-user store:
recent vault saves are positives and matched discovery-queue items not yet
written to the vault are negatives. Matching prefers the same source and then
uses nearest visual neighbors as hard cross-source fallbacks. The grounded
portrait is scored in the existing SigLIP image/text space, one short claim at
a time.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np

from .config import InterestConfig
from .interest import InterestSnapshot, ProfileScore
from .synthesis import evidence_is_fresh


class ProfileEvaluationUnavailable(RuntimeError):
    """Raised when a regeneration cannot produce its required ranking score."""


@dataclass
class ProfileCohort:
    positives: list[dict]
    negatives: list[dict]
    heldout_note_ids: set[str]
    reused_previous: bool


def _note_visual_map(notes: list[dict], saved: list[dict]) -> dict[str, str]:
    by_path = {item["note_path"]: item["id"] for item in saved if item.get("note_path")}
    saved_ids = {item["id"] for item in saved}
    out: dict[str, str] = {}
    for note in notes:
        visual_id = by_path.get(note.get("source_path", ""))
        if visual_id is None and f"yt:{note['id']}" in saved_ids:
            visual_id = f"yt:{note['id']}"
        if visual_id is None and note.get("source") == "tiktok":
            source_path = note.get("source_path", "")
            visual_id = next(
                (
                    item_id
                    for item_id in saved_ids
                    if item_id.startswith("tt:")
                    and item_id.removeprefix("tt:").removesuffix("-thumb") in source_path
                ),
                None,
            )
        if visual_id:
            out[note["id"]] = visual_id
    return out


def _resolve_previous(
    previous: InterestSnapshot | None,
    saved_by_id: dict[str, dict],
    pending_by_id: dict[str, dict],
    visual_to_note: dict[str, str],
) -> ProfileCohort | None:
    score = previous.profile_score if previous else None
    if score is None:
        return None
    if not all(item_id in saved_by_id for item_id in score.positive_ids):
        return None
    if not all(item_id in pending_by_id for item_id in score.negative_ids):
        return None
    return ProfileCohort(
        positives=[saved_by_id[item_id] for item_id in score.positive_ids],
        negatives=[pending_by_id[item_id] for item_id in score.negative_ids],
        heldout_note_ids={
            visual_to_note[item_id] for item_id in score.positive_ids if item_id in visual_to_note
        },
        reused_previous=True,
    )


def _matched_negatives(positives: list[dict], pending: list[dict], per_positive: int) -> list[dict]:
    """Pick unique hard negatives, preferring same-source visual neighbors."""
    chosen: list[dict] = []
    used: set[str] = set()
    for positive in positives:
        positive_vector = np.asarray(positive["embedding"], dtype=float)
        positive_vector /= max(np.linalg.norm(positive_vector), 1e-12)

        def ranked(candidates: list[dict]) -> list[dict]:
            def key(item: dict) -> tuple[float, str]:
                vector = np.asarray(item["embedding"], dtype=float)
                vector /= max(np.linalg.norm(vector), 1e-12)
                return (
                    -float(vector @ positive_vector),
                    hashlib.sha256(item["id"].encode()).hexdigest(),
                )

            return sorted(candidates, key=key)

        available = [item for item in pending if item["id"] not in used]
        same_source = [
            item for item in available if item.get("source", "") == positive.get("source", "")
        ]
        selected = ranked(same_source)[:per_positive]
        if len(selected) < per_positive:
            selected_ids = {item["id"] for item in selected}
            fallback = [item for item in available if item["id"] not in selected_ids]
            selected.extend(ranked(fallback)[: per_positive - len(selected)])
        chosen.extend(selected)
        used.update(item["id"] for item in selected)
    return chosen


def build_cohort(
    snapshot: InterestSnapshot,
    notes: list[dict],
    levels: list[int],
    saved: list[dict],
    pending: list[dict],
    cfg: InterestConfig,
    previous: InterestSnapshot | None = None,
) -> ProfileCohort | None:
    """Build or reuse a deterministic saved-positive/pending-negative cohort."""
    saved_by_id = {item["id"]: item for item in saved}
    pending_by_id = {item["id"]: item for item in pending}
    note_to_visual = _note_visual_map(notes, saved)
    visual_to_note = {v: k for k, v in note_to_visual.items()}

    reused = _resolve_previous(previous, saved_by_id, pending_by_id, visual_to_note)
    if reused is not None:
        return reused

    cited_ids = {
        evidence_id for claim in snapshot.portrait_claims for evidence_id in claim.evidence_ids
    } | {evidence_id for theme in snapshot.themes for evidence_id in theme.evidence_ids}
    eligible = [
        (note, level, note_to_visual.get(note["id"]))
        for note, level in zip(notes, levels)
        if note_to_visual.get(note["id"])
        and evidence_is_fresh(
            note.get("captured_at", ""),
            snapshot.generated_at,
            cfg.decay_half_life_days,
        )
    ]
    # Prefer recent saves the generated prose did not cite. This makes the
    # evaluation query evidence-disjoint from its held-out positives.
    # Stable passes make id the deterministic tie-breaker, signal level a
    # same-time preference, capture time the recency preference, and citation
    # status the primary preference. Saving is itself the positive action; a
    # written thought is useful but not required.
    eligible.sort(key=lambda row: row[0]["id"])
    eligible.sort(key=lambda row: row[1], reverse=True)
    eligible.sort(key=lambda row: row[0].get("captured_at", ""), reverse=True)
    eligible.sort(key=lambda row: row[0]["id"] in cited_ids)
    chosen = eligible[: cfg.profile_eval_positives]
    if not chosen:
        return None

    positives = [saved_by_id[visual_id] for _, _, visual_id in chosen]
    negatives = _matched_negatives(positives, pending, cfg.profile_eval_negatives_per_positive)
    if not negatives:
        return None
    return ProfileCohort(
        positives=positives,
        negatives=negatives,
        heldout_note_ids={note["id"] for note, _, _ in chosen},
        reused_previous=False,
    )


def _multi_positive_ndcg(scores: np.ndarray, positive_count: int) -> float:
    order = np.argsort(-scores, kind="stable")
    positive = set(range(positive_count))
    dcg = sum(
        1.0 / math.log2(rank + 2)
        for rank, candidate_index in enumerate(order)
        if int(candidate_index) in positive
    )
    ideal = sum(1.0 / math.log2(rank + 2) for rank in range(positive_count))
    return dcg / ideal if ideal else 0.0


def score_claims(
    claims: list[str],
    positives: list[dict],
    negatives: list[dict],
    embed_texts,
) -> float:
    """Rank candidates by max cosine to any short portrait/theme claim."""
    if not claims or not positives or not negatives:
        raise ValueError("profile evaluation needs claims, positives, and negatives")
    query = np.asarray(embed_texts(claims), dtype=float)
    candidates = np.asarray([item["embedding"] for item in positives + negatives], dtype=float)
    query /= np.maximum(np.linalg.norm(query, axis=1, keepdims=True), 1e-12)
    candidates /= np.maximum(np.linalg.norm(candidates, axis=1, keepdims=True), 1e-12)
    scores = (candidates @ query.T).max(axis=1)
    return _multi_positive_ndcg(scores, len(positives))


def evaluate_snapshot(
    snapshot: InterestSnapshot,
    notes: list[dict],
    levels: list[int],
    cfg: InterestConfig,
    previous: InterestSnapshot | None = None,
    *,
    saved: list[dict] | None = None,
    pending: list[dict] | None = None,
    embed_texts=None,
) -> ProfileScore | None:
    """Score and compare one regeneration; dependencies are injectable for tests."""
    if saved is None or pending is None:
        from .store import get_profile_visual_pool

        saved = get_profile_visual_pool(pending=False)
        pending = get_profile_visual_pool(pending=True)
    if embed_texts is None:
        from .visual import embed_texts as _embed_texts

        embed_texts = _embed_texts

    cohort = build_cohort(snapshot, notes, levels, saved, pending, cfg, previous)
    if cohort is None:
        return None
    claims = [
        claim.text
        for claim in snapshot.portrait_claims
        if not set(claim.evidence_ids) & cohort.heldout_note_ids
    ] + [
        theme.summary
        for theme in snapshot.themes
        if not set(theme.evidence_ids) & cohort.heldout_note_ids
    ]
    claims = [claim.strip() for claim in claims if claim.strip()]
    if not claims:
        return None

    score = score_claims(claims, cohort.positives, cohort.negatives, embed_texts)
    from .visual import MODEL_ID, MODEL_REVISION

    candidate_ids = [item["id"] for item in cohort.positives + cohort.negatives]
    fingerprint = hashlib.sha256(
        json.dumps(candidate_ids, separators=(",", ":")).encode()
    ).hexdigest()
    previous_score = previous.profile_score if previous else None
    comparable = bool(
        cohort.reused_previous
        and previous_score
        and previous_score.candidate_fingerprint == fingerprint
        and previous_score.encoder == f"{MODEL_ID}@{MODEL_REVISION}"
    )
    delta = score - previous_score.score if comparable and previous_score else None
    warning = None
    if delta is not None and delta < -cfg.profile_eval_regression_tolerance:
        warning = (
            f"profile ranking score dropped {abs(delta):.4f} "
            f"({previous_score.score:.4f} -> {score:.4f})"
        )
    return ProfileScore(
        score=round(score, 6),
        positive_ids=[item["id"] for item in cohort.positives],
        negative_ids=[item["id"] for item in cohort.negatives],
        candidate_fingerprint=fingerprint,
        encoder=f"{MODEL_ID}@{MODEL_REVISION}",
        claim_count=len(claims),
        comparable_to_previous=comparable,
        previous_score=previous_score.score if comparable and previous_score else None,
        delta=round(delta, 6) if delta is not None else None,
        warning=warning,
    )
