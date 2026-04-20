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
