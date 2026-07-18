import ytk.interest as interest
from ytk.interest import (
    InterestSnapshot,
    PortraitClaim,
    ProfileScore,
    Theme,
    load_latest,
    save_snapshot,
)


def _sample() -> InterestSnapshot:
    return InterestSnapshot(
        generated_at="2026-06-02T00:00:00+00:00",
        note_count=2,
        themes=[Theme(id="creative-coding", label="Creative coding", summary="s",
                      weight=1.0, note_ids=["a", "b"], exemplar_titles=["A", "B"])],
        connections=[],
        profile_markdown="You are into creative coding.",
        portrait_claims=[
            PortraitClaim(text="You build creative tools.", evidence_ids=["a"])
        ],
        evidence_captured_at={"a": "2026-06-01T00:00:00+00:00"},
        decay_half_life_days=90,
        profile_score=ProfileScore(
            score=0.75,
            positive_ids=["ig:positive"],
            negative_ids=["ig:negative"],
            candidate_fingerprint="cohort",
            encoder="siglip@test",
            claim_count=1,
        ),
    )


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(interest, "_INTEREST_DIR", tmp_path)
    snap = _sample()
    stamped = save_snapshot(snap, "20260602T000000Z")

    assert stamped.exists()
    assert (tmp_path / "latest.json").exists()
    loaded = load_latest()
    assert loaded is not None
    assert loaded.note_count == 2
    assert loaded.themes[0].label == "Creative coding"
    assert loaded.profile_markdown == "You are into creative coding."
    assert loaded.portrait_claims[0].evidence_ids == ["a"]
    assert loaded.profile_score is not None
    assert loaded.profile_score.score == 0.75


def test_load_latest_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(interest, "_INTEREST_DIR", tmp_path)
    assert load_latest() is None
