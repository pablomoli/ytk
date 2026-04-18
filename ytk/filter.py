"""Pre- and post-enrichment filter checks for ytk ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .enrich import Enrichment


@dataclass
class FilterFailure:
    reason: str
    detail: str


@dataclass
class FilterResult:
    passed: bool
    failures: list[FilterFailure] = field(default_factory=list)


def check_pre_transcript(meta: dict, cfg: Config) -> FilterResult:
    """
    Structural checks on metadata alone — runs before transcript fetch.
    Currently checks: min_duration, max_duration.
    Captions availability is checked separately during transcript fetch.
    """
    failures: list[FilterFailure] = []
    f = cfg.filters
    duration = meta.get("duration", 0) or 0

    if f.min_duration and duration < f.min_duration:
        failures.append(FilterFailure(
            reason="min_duration",
            detail=f"Duration {_fmt(duration)} is below minimum {_fmt(f.min_duration)}.",
        ))

    if f.max_duration is not None and duration > f.max_duration:
        failures.append(FilterFailure(
            reason="max_duration",
            detail=f"Duration {_fmt(duration)} exceeds maximum {_fmt(f.max_duration)}.",
        ))

    return FilterResult(passed=not failures, failures=failures)


def check_post_enrichment(enrichment: Enrichment, cfg: Config) -> FilterResult:
    """
    Semantic check on enrichment output — runs after Haiku enrichment.
    If interest_tags is non-empty, at least one enrichment tag must match.
    Matching is case-insensitive and normalises hyphens/underscores.
    """
    failures: list[FilterFailure] = []
    allowed = cfg.filters.interest_tags

    if allowed:
        def _norm(t: str) -> str:
            return t.lower().replace("-", " ").replace("_", " ")

        allowed_norm = {_norm(t) for t in allowed}
        matched = [t for t in enrichment.interest_tags if _norm(t) in allowed_norm]

        if not matched:
            failures.append(FilterFailure(
                reason="interest_tags",
                detail=(
                    f"No interest tags matched. "
                    f"Video tags: {enrichment.interest_tags or ['(none)']}. "
                    f"Your tags: {allowed}."
                ),
            ))

    return FilterResult(passed=not failures, failures=failures)


def _fmt(seconds: int | float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"
