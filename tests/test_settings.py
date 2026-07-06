"""Tests for the settings surface: config persistence, /api/settings, cadence."""

from __future__ import annotations

import pytest
import yaml

from ytk.config import ColorRule, Config, load_config, save_config


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    monkeypatch.setenv("YTK_CONFIG", str(path))
    return path


def test_save_config_round_trips(cfg_path):
    cfg = Config()
    cfg.hub.port = 7000
    cfg.map.color_rules = [ColorRule(query="go", color="#e2b04a")]
    cfg.map.presets = {"dev": [ColorRule(query="rust", color="#e0785a")]}
    save_config(cfg)

    loaded = load_config()
    assert loaded.hub.port == 7000
    assert loaded.map.color_rules[0].query == "go"
    assert loaded.map.presets["dev"][0].color == "#e0785a"
    # file is plain YAML a human can still edit
    raw = yaml.safe_load(cfg_path.read_text())
    assert raw["hub"]["port"] == 7000


def test_color_rule_rejects_bad_hex():
    with pytest.raises(Exception):
        ColorRule(query="x", color="red")


@pytest.fixture
def hub(tmp_path, monkeypatch, cfg_path):
    import ytk.ui.hub as hub_mod

    brain = tmp_path / "brain"
    (brain / "sources").mkdir(parents=True)
    monkeypatch.setattr("ytk.vault._get_brain_path", lambda: brain)
    monkeypatch.setattr(hub_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(hub_mod, "IG_PULL", lambda state: 1)
    monkeypatch.setattr(hub_mod, "YT_FETCH", lambda: [])
    monkeypatch.setattr(hub_mod, "YT_IS_PROCESSED", lambda vid: False)
    monkeypatch.setattr(hub_mod, "PIN_FETCH", lambda: [])
    monkeypatch.setattr(hub_mod, "IM_FETCH", lambda: [])
    return hub_mod


@pytest.fixture
def client(hub):
    from fastapi.testclient import TestClient

    from ytk.ui.server import app

    return TestClient(app)


def test_per_source_cadence(hub):
    cfg = Config()
    cfg.hub.cadence_minutes = {"instagram": 0, "youtube": 15, "pinterest": 15, "imessage": 15}
    save_config(cfg)

    first = hub.refresh_sources()
    assert first["skipped"] is False

    # instagram (cadence 0) is due again immediately; the others are throttled
    second = hub.refresh_sources()
    assert second["skipped"] is False
    assert second["instagram"] == 1
    assert sorted(second["skipped_sources"]) == ["imessage", "pinterest", "youtube"]


def test_favicon_renders_configured_glyph(client):
    cfg = Config()
    cfg.hub.favicon = "Y"
    save_config(cfg)
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert ">Y</text>" in r.text


def test_settings_get_shape(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["hub"]["port"] == 6969
    assert "hub.port" in body["meta"]["restart_required_fields"]
    assert "last_pulls" in body["meta"]


def test_settings_put_validates_inline(client, cfg_path):
    bad = {"hub": {"port": "nope"}, "map": {"color_rules": [{"query": "x", "color": "red"}]}}
    r = client.put("/api/settings", json=bad)
    assert r.status_code == 422
    locs = {e["loc"] for e in r.json()["detail"]}
    assert "hub.port" in locs
    assert "map.color_rules.0.color" in locs
    assert not cfg_path.exists()  # nothing persisted on validation failure


def test_settings_put_saves_and_flags_restart(client, cfg_path):
    cfg = Config().model_dump(mode="json")
    cfg["hub"]["port"] = 7777
    cfg["whisper_model"] = "small"
    r = client.put("/api/settings", json=cfg)
    assert r.status_code == 200
    assert r.json() == {"saved": True, "restart_required": True}
    assert load_config().whisper_model == "small"
