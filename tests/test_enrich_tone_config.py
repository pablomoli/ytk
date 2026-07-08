"""Tests for tone preamble config and wiring (Task 4)."""

import ytk.enrich as e
from ytk.config import Config


def test_config_has_enrich_tone_default_empty():
    """HubConfig.enrich_tone defaults to empty string."""
    assert Config().hub.enrich_tone == ""


def test_enrich_content_pulls_tone_from_config(monkeypatch):
    """When tone is not passed, enrich_content pulls from config.hub.enrich_tone."""
    cfg = Config()
    cfg.hub.enrich_tone = "terse and technical"
    monkeypatch.setattr(e, "load_config", lambda: cfg)
    captured = {}
    monkeypatch.setattr(
        e,
        "run_structured",
        lambda s, u, sc, add_dirs=None, **kw: captured.update(system=s)
        or {
            "thesis": "t",
            "summary": "s",
            "key_concepts": [],
            "insights": [],
            "interest_tags": [],
            "key_moments": [],
        },
    )
    e.enrich_content("body", "web")
    assert "terse and technical" in captured["system"]


def test_explicit_tone_overrides_config(monkeypatch):
    """When tone is explicitly passed, it overrides config.hub.enrich_tone."""
    cfg = Config()
    cfg.hub.enrich_tone = "from config"
    monkeypatch.setattr(e, "load_config", lambda: cfg)
    captured = {}
    monkeypatch.setattr(
        e,
        "run_structured",
        lambda s, u, sc, add_dirs=None, **kw: captured.update(system=s)
        or {
            "thesis": "t",
            "summary": "s",
            "key_concepts": [],
            "insights": [],
            "interest_tags": [],
            "key_moments": [],
        },
    )
    e.enrich_content("body", "web", tone="explicit")
    assert "explicit" in captured["system"] and "from config" not in captured["system"]
