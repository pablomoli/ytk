"""Tests for InterestConfig defaults."""

from __future__ import annotations

from ytk.config import Config


def test_interest_config_defaults():
    cfg = Config()
    assert cfg.interest.cluster_min == 3
    assert cfg.interest.cluster_max == 24
