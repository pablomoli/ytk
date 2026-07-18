"""Tests for InterestConfig defaults."""

from __future__ import annotations

from ytk.config import Config


def test_interest_config_defaults():
    cfg = Config()
    assert cfg.interest.cluster_min == 3
    assert cfg.interest.cluster_max == 24
    assert cfg.interest.content_sources == ["instagram", "tiktok", "web"]
    assert cfg.interest.decay_half_life_days == 90.0
    assert cfg.interest.profile_eval_positives == 8
    assert cfg.interest.profile_eval_negatives_per_positive == 3
