# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Load and validate ytk configuration from ~/.ytk/config.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class FilterConfig(BaseModel):
    min_duration: int = Field(default=60, description="Minimum video duration in seconds.")
    max_duration: int | None = Field(
        default=None, description="Maximum video duration in seconds. Null means no limit."
    )
    require_captions: bool = Field(default=True, description="Reject videos with no captions.")
    interest_tags: list[str] = Field(
        default_factory=list,
        description="At least one tag must match enrichment output. Empty list allows all.",
    )


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
        description="Confidence weighting slope: sample weight = 1 + alpha * signal level r. 0 disables weighting. Fitted 2026-07-05 against the held-out-save target E2 later falsified; E5 (docs/assets/27) measured the inherited value doing real unjustified work. E6 (docs/assets/28) dissolved the question: with playlist intent recorded, r is near-uniform and alpha only scales the take boost — the ranking is stable across alpha 0-31 (tau 0.897).",
    )
    explicit_min: int = Field(
        default=5,
        description="Minimum thought-carrying items (r >= 2) before the explicit interest channel activates.",
    )
    decay_half_life_days: float = Field(
        default=90.0,
        gt=0,
        description="Capture-time half-life for recency-decayed theme weight and the maximum age of a claim's freshest evidence.",
    )
    fresh_window_days: float = Field(
        default=14.0,
        gt=0,
        description="Display-only window for the per-theme 'recent' overlay on the profile page. Separate from decay_half_life_days on purpose: a young corpus sits entirely inside the 90-day half-life, so an overlay tied to it reads 98% fresh and carries no signal, while shortening the half-life itself would lurch theme weights and fail portrait-claim grounding.",
    )
    profile_eval_positives: int = Field(
        default=8,
        ge=1,
        description="Number of recent, deliberately saved visual items in the fixed profile-evaluation cohort.",
    )
    profile_eval_negatives_per_positive: int = Field(
        default=3,
        ge=1,
        description="Source-matched pending (not-yet-vaulted) candidates per held-out save in the profile evaluation.",
    )
    profile_eval_regression_tolerance: float = Field(
        default=0.02,
        ge=0,
        le=1,
        description="Minimum comparable nDCG drop that makes ytk profile print a warning.",
    )


class ColorRule(BaseModel):
    """One map color rule: notes matching `query` paint `color`.

    Rules are ordered; the first matching rule wins (Obsidian Groups model).
    """

    query: str = Field(
        description="Substring/tag query matched against a note's path, title, and tags."
    )
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$", description="Hex color, e.g. #e2b04a.")


class MapConfig(BaseModel):
    """Configuration for the brain map (/map)."""

    color_rules: list[ColorRule] = Field(
        default_factory=list,
        description="Ordered first-match-wins color rules consumed by the map.",
    )
    presets: dict[str, list[ColorRule]] = Field(
        default_factory=dict,
        description="Saved color-rule presets by name.",
    )


class HubConfig(BaseModel):
    """Configuration for the ingest hub UI."""

    host: str = Field(default="127.0.0.1", description="Hub bind address.")
    port: int = Field(default=6969, description="Hub port (memorable on purpose).")
    favicon: str = Field(
        default="✦", description="Character or emoji rendered as the hub tab icon."
    )
    cadence_minutes: dict[str, int] = Field(
        default_factory=lambda: {
            "instagram": 15,
            "youtube": 15,
            "pinterest": 15,
            "imessage": 15,
            # Daily: favorites scraping rides the user's real TikTok session,
            # so anything page-load-shaped would be bot-shaped traffic.
            "tiktok": 1440,
        },
        description="Auto-pull throttle per discovery source, in minutes.",
    )
    imessage_gap_minutes: int = Field(
        default=20,
        description="Silence gap that closes an iMessage self-note session into one inbox node.",
    )
    tags: list[str] = Field(
        default_factory=lambda: [
            "design",
            "music",
            "build-idea",
            "dev-tools",
            "movies",
            "anime",
            "fitness",
            "reference",
        ],
        description="Predefined annotation tags shown as chips in /inbox.",
    )
    pinterest_feeds: list[str] = Field(
        default_factory=list,
        description="Pinterest board RSS URLs pulled into the ingest queue.",
    )
    enrich_tone: str = Field(
        default="",
        description="User voice preamble prefixed to every enrichment prompt. Shapes tone only; anti-fluff and faithfulness rules always follow it and cannot be overridden.",
    )


class Config(BaseModel):
    filters: FilterConfig = Field(default_factory=FilterConfig)
    hub: HubConfig = Field(default_factory=HubConfig)
    search_reflected_boost: float = Field(
        default=0.0,
        description="Fraction by which a reflected item's distance shrinks in ranking (#98). "
        "0 disables. Any nonzero default must first pass `ytk eval`.",
    )
    whisper_model: str = Field(
        default="base", description="faster-whisper model size: base | small | medium | large"
    )
    tiktok_username: str | None = Field(
        default=None,
        description="TikTok handle whose favorites tab the discovery fetcher syncs; unset disables the source.",
    )
    reddit_subreddits: list[str] = Field(
        default_factory=list,
        description="Allowlist of subreddits to browse into the queue. Empty disables the source. Saved posts are never read.",
    )
    reddit_sort: str = Field(
        default="top", description="Reddit listing sort: hot | top | new | rising."
    )
    reddit_window: str = Field(
        default="week", description="Time window for top sort: day | week | month | year | all."
    )
    reddit_limit: int = Field(default=25, description="Max posts pulled per subreddit per sync.")
    autoingest_enabled: bool = Field(
        default=False,
        description="Enable the scheduled profile-matched auto-ingest of pending items.",
    )
    autoingest_count: int = Field(
        default=30,
        description="Max items the auto-ingest pulls per run (hard-capped regardless).",
    )
    autoingest_cadence: str = Field(
        default="weekly",
        description="Auto-ingest schedule: daily | weekly.",
    )
    memo_notify: list[str] = Field(
        default_factory=list,
        description="Memo notification backends (tmux|macos|sketchybar); empty = focus-aware auto",
    )
    github_repos: list[str] = Field(
        default_factory=list,
        description="GitHub repos (owner/name) available when creating issues via ytk triage.",
    )
    interest: InterestConfig = Field(default_factory=InterestConfig)
    map: MapConfig = Field(default_factory=MapConfig)


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


def save_config(config: Config, path: Path | None = None) -> Path:
    """Persist the full config to YAML (default: ~/.ytk/config.yaml)."""
    config_path = path or Path(os.environ.get("YTK_CONFIG", str(_DEFAULT_CONFIG_PATH)))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return config_path
