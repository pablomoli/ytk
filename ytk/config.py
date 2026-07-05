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


class InterestConfig(BaseModel):
    """Configuration for the interest-model synthesis engine."""

    cluster_min: int = Field(default=3, description="Minimum number of theme clusters.")
    cluster_max: int = Field(default=24, description="Maximum number of theme clusters.")
    content_sources: list[str] = Field(
        default_factory=lambda: ["instagram", "tiktok", "web"],
        description="doc_id prefixes from the memories collection to include in the interest profile (besides YouTube videos).",
    )
    alpha: float = Field(
        default=7.0,
        description="Confidence weighting slope: sample weight = 1 + alpha * signal level r. 0 disables weighting. Fitted 2026-07-05 via 5-fold held-out-save retrieval (plateau alpha 7-31; 7 keeps passive items meaningful).",
    )
    explicit_min: int = Field(
        default=5,
        description="Minimum thought-carrying items (r >= 2) before the explicit interest channel activates.",
    )


class HubConfig(BaseModel):
    """Configuration for the ingest hub UI."""

    tags: list[str] = Field(
        default_factory=lambda: [
            "design", "music", "build-idea", "dev-tools",
            "movies", "anime", "fitness", "reference",
        ],
        description="Predefined annotation tags shown as chips in /inbox.",
    )
    pinterest_feeds: list[str] = Field(
        default_factory=list,
        description="Pinterest board RSS URLs pulled into the ingest queue.",
    )


class Config(BaseModel):
    filters: FilterConfig = Field(default_factory=FilterConfig)
    hub: HubConfig = Field(default_factory=HubConfig)
    whisper_model: str = Field(default="base", description="faster-whisper model size: base | small | medium | large")
    memo_notify: list[str] = Field(
        default_factory=list,
        description="Memo notification backends (tmux|macos|sketchybar); empty = focus-aware auto",
    )
    github_repos: list[str] = Field(default_factory=list, description="GitHub repos (owner/name) available when creating issues via ytk triage.")
    interest: InterestConfig = Field(default_factory=InterestConfig)


_DEFAULT_CONFIG_PATH = Path.home() / ".ytk" / "config.yaml"
_ALIAS_PATH = Path.home() / ".ytk" / "tag-aliases.yaml"
_alias_cache: tuple[float, dict[str, str]] | None = None


def tag_aliases() -> dict[str, str]:
    """Tag merge decisions from the hub /tags review, as {variant: canonical}.

    Consulted wherever tags are normalized, so an accepted merge holds
    forever: if enrichment re-coins a retired variant it lands as the
    canonical tag. Cached on file mtime so long-running processes see edits.
    """
    global _alias_cache
    path = Path(os.environ.get("YTK_TAG_ALIASES", str(_ALIAS_PATH)))
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    if _alias_cache is None or _alias_cache[0] != mtime:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        _alias_cache = (mtime, {str(k): str(v) for k, v in raw.items()})
    return _alias_cache[1]


def save_tag_aliases(new: dict[str, str]) -> None:
    """Merge accepted variant->canonical pairs into the alias map."""
    merged = {**tag_aliases(), **new}
    # collapse chains (a->b then b->c must resolve a->c) so lookups stay 1-hop
    merged = {k: merged.get(v, v) for k, v in merged.items() if k != merged.get(v, v)}
    path = Path(os.environ.get("YTK_TAG_ALIASES", str(_ALIAS_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(merged, sort_keys=True), encoding="utf-8")


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
