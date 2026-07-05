"""Tests for ytk configuration."""

from ytk.config import Config, load_config


def test_default_whisper_model():
    cfg = Config()
    assert cfg.whisper_model == "base"


def test_whisper_model_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("whisper_model: small\n", encoding="utf-8")
    cfg = load_config(cfg_file)
    assert cfg.whisper_model == "small"


def test_github_repos_default_empty():
    cfg = Config()
    assert cfg.github_repos == []


def test_github_repos_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "github_repos:\n  - melocoton/ytk\n  - melocoton/epic-map\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.github_repos == ["melocoton/ytk", "melocoton/epic-map"]


def test_hub_buckets_default_and_override(tmp_path, monkeypatch):
    from ytk.config import load_config

    cfg = load_config(tmp_path / "missing.yaml")
    assert "design" in cfg.hub.buckets and "music" in cfg.hub.buckets

    p = tmp_path / "config.yaml"
    p.write_text("hub:\n  buckets:\n    - lifting\n    - recipes\n")
    cfg = load_config(p)
    assert cfg.hub.buckets == ["lifting", "recipes"]
