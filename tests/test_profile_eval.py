"""BUMP-style profile-text ranking over fixed saved/pending visual cohorts."""

from __future__ import annotations

import pytest

from ytk.config import InterestConfig
from ytk.interest import InterestSnapshot, PortraitClaim, Theme
from ytk.profile_eval import build_cohort, evaluate_snapshot, score_claims


def _snapshot(text="visual systems", evidence=None):
    evidence = evidence or ["support"]
    return InterestSnapshot(
        generated_at="2026-07-18T12:00:00+00:00",
        note_count=2,
        themes=[Theme(
            id="visual", label="Visual", summary=text, weight=1.0,
            note_ids=["support", "held"], exemplar_titles=[],
            evidence_ids=evidence,
        )],
        profile_markdown=text,
        portrait_claims=[PortraitClaim(text=text, evidence_ids=evidence)],
    )


def _data():
    notes = [
        {"id": "support", "source_path": "/vault/support.md", "source": "instagram",
         "captured_at": "2026-07-16T00:00:00+00:00"},
        {"id": "held", "source_path": "/vault/held.md", "source": "instagram",
         "captured_at": "2026-07-17T00:00:00+00:00"},
    ]
    saved = [
        {"id": "ig:support", "note_path": "/vault/support.md", "source": "instagram",
         "embedding": [1.0, 0.0]},
        {"id": "ig:held", "note_path": "/vault/held.md", "source": "instagram",
         "embedding": [1.0, 0.0]},
    ]
    pending = [
        {"id": "https://instagram.test/negative", "note_path": "", "source": "instagram",
         "embedding": [0.0, 1.0]},
    ]
    return notes, saved, pending


def test_score_claims_is_multi_positive_ndcg_over_actual_text_embedding():
    positives = [{"embedding": [1.0, 0.0]}]
    negatives = [{"embedding": [0.0, 1.0]}]
    assert score_claims(
        ["matching"], positives, negatives, lambda _: [[1.0, 0.0]]
    ) == 1.0
    assert score_claims(
        ["opposite"], positives, negatives, lambda _: [[0.0, 1.0]]
    ) == pytest.approx(1 / __import__("math").log2(3))


def test_cohort_prefers_uncited_recent_save_and_matches_negative_source():
    notes, saved, pending = _data()
    cfg = InterestConfig(
        profile_eval_positives=1, profile_eval_negatives_per_positive=1
    )
    cohort = build_cohort(
        _snapshot(evidence=["support"]), notes, [1, 1], saved, pending, cfg
    )
    assert cohort is not None
    assert [item["id"] for item in cohort.positives] == ["ig:held"]
    assert [item["source"] for item in cohort.negatives] == ["instagram"]
    assert cohort.heldout_note_ids == {"held"}


def test_cohort_joins_legacy_tiktok_visual_without_note_path():
    note_path = "/vault/tiktok/user-2026-07-17-1234567890123456789-title.md"
    notes = [{
        "id": "tiktok_note",
        "source_path": note_path,
        "source": "tiktok",
        "captured_at": "2026-07-17T00:00:00+00:00",
    }]
    saved = [{
        "id": "tt:1234567890123456789-thumb",
        "note_path": "",
        "source": "tiktok",
        "embedding": [1.0, 0.0],
    }]
    pending = [{
        "id": "https://tiktok.test/negative",
        "note_path": "",
        "source": "tiktok",
        "embedding": [0.0, 1.0],
    }]
    cfg = InterestConfig(
        profile_eval_positives=1, profile_eval_negatives_per_positive=1
    )

    cohort = build_cohort(_snapshot(), notes, [1], saved, pending, cfg)

    assert cohort is not None
    assert [item["id"] for item in cohort.positives] == [
        "tt:1234567890123456789-thumb"
    ]


def test_recent_save_does_not_require_a_written_thought():
    notes, saved, pending = _data()
    cfg = InterestConfig(
        profile_eval_positives=1, profile_eval_negatives_per_positive=1
    )

    cohort = build_cohort(_snapshot(), notes, [0, 0], saved, pending, cfg)

    assert cohort is not None
    assert [item["id"] for item in cohort.positives] == ["ig:held"]


def test_cohort_uses_nearest_visual_negative_when_source_is_unavailable():
    notes = [{
        "id": "video",
        "source": "youtube",
        "captured_at": "2026-07-17T00:00:00+00:00",
    }]
    saved = [{
        "id": "yt:video",
        "source": "youtube",
        "embedding": [1.0, 0.0],
        "note_path": "",
    }]
    pending = [
        {"id": "far", "source": "instagram", "embedding": [0.0, 1.0]},
        {"id": "near", "source": "instagram", "embedding": [0.9, 0.1]},
    ]
    cfg = InterestConfig(
        profile_eval_positives=1, profile_eval_negatives_per_positive=1
    )

    cohort = build_cohort(_snapshot(), notes, [0], saved, pending, cfg)

    assert cohort is not None
    assert [item["id"] for item in cohort.negatives] == ["near"]


def test_eval_reuses_previous_cohort_and_warns_on_comparable_drop():
    notes, saved, pending = _data()
    cfg = InterestConfig(
        profile_eval_positives=1,
        profile_eval_negatives_per_positive=1,
        profile_eval_regression_tolerance=0.02,
    )
    first = _snapshot("matching", evidence=["support"])
    first.profile_score = evaluate_snapshot(
        first, notes, [1, 1], cfg, saved=saved, pending=pending,
        embed_texts=lambda claims: [[1.0, 0.0] for _ in claims],
    )
    assert first.profile_score is not None
    assert first.profile_score.score == 1.0

    second = _snapshot("opposite", evidence=["support"])
    result = evaluate_snapshot(
        second, notes, [1, 1], cfg, previous=first,
        saved=saved, pending=pending,
        embed_texts=lambda claims: [[0.0, 1.0] for _ in claims],
    )
    assert result is not None
    assert result.comparable_to_previous is True
    assert result.delta is not None and result.delta < 0
    assert result.warning and "dropped" in result.warning
