"""Load and validate ytk configuration from ~/.ytk/config.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class FilterConfig(BaseModel):
    min_duration: int = Field(default=60, description="Minimum video duration in seconds.")
    max_duration: int | None = Field(default=None, description="Maximum video duration in seconds. Null means no limit.")
    require_captions: bool = Field(default=True, description="Reject videos with no captions.")
    interest_tags: list[str] = Field(default_factory=list, description="At least one tag must match enrichment output. Empty list allows all.")


class Config(BaseModel):
    filters: FilterConfig = Field(default_factory=FilterConfig)
    whisper_model: str = Field(default="base", description="faster-whisper model size: base | small | medium | large")
    github_repos: list[str] = Field(default_factory=list, description="GitHub repos (owner/name) available when creating issues via ytk triage.")


_DEFAULT_CONFIG_PATH = Path.home() / ".ytk" / "config.yaml"


def load_config(path: Path | None = None) -> Config:
    """
    Load config from path (default: ~/.ytk/config.yaml).
    Missing file returns defaults. Unknown keys are silently ignored.
    """
    config_path = path or Path(os.environ.get("YTK_CONFIG", str(_DEFAULT_CONFIG_PATH)))

    if not config_path.exists():
        return Config()

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return Config.model_validate(raw)
