"""Deterministic domain assignment for the brain map's everything view.

A domain is the controlled top-level grouping axis: the owning project for
session/memory notes (parsed from paths — no LLM), the interest-profile theme
for consumed content, and `other` for the small residue. Pure functions;
scripts/build_map.py wires them to real vectors and the theme snapshot.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

CONTENT_CATS = frozenset(
    {"youtube", "instagram", "tiktok", "pinterest", "web", "screenshots"}
)
OTHER = "other"
_SUMMARY_RE = re.compile(r"^summary-\d{4}-\d{2}-\d{2}-(.+?)-\d+\.md$")
_USER_PREFIX_RE = re.compile(r"^users-melocoton(?:-developer)?-")


def project_from_path(source_path: str) -> str | None:
    """Owning project of a note, from its vault path.

    claude-mem session summaries encode it in the filename
    (summary-YYYY-MM-DD-{project}-{id}.md); memory atoms and project notes
    carry it as their folder slug.
    """
    if not source_path:
        return None
    parts = Path(source_path).parts
    for anchor in ("memories", "projects"):
        if anchor in parts:
            i = parts.index(anchor)
            if i + 1 >= len(parts) - 1:
                return None
            slug = parts[i + 1].lower()
            m = _SUMMARY_RE.match(parts[-1])
            if slug == "claude-mem" and m:
                project = m.group(1).lower()
                # Untitled sessions parse to the literal "session" - a
                # meaningless pseudo-domain, not a real project.
                return None if project == "session" else project
            return slug
    return None


def normalize_slug(slug: str, established: set[str]) -> str:
    """Canonical project name for a raw folder slug.

    Strips the absolute-path prefix seeded by the session scraper and folds
    worktree/branch variants (epicmap-claude-worktrees-...) into their base
    project when that project is already established (frequent enough on its
    own). Longest established prefix wins.
    """
    slug = _USER_PREFIX_RE.sub("", slug.lower()).lstrip(".")
    for base in sorted(established, key=len, reverse=True):
        if slug != base and slug.startswith(base + "-"):
            return base
    return slug


def domain_labels(
    metas: list[dict],
    content_theme: dict[int, int],
    theme_labels: list[str],
    min_size: int = 40,
) -> list[str]:
    """Per-point domain label.

    content_theme maps point index -> theme index (-1 for below the
    confidence floor) for content-category points. Two passes: raw project
    counts establish the collapse targets, then everything below min_size
    merges into `other`.
    """
    raw: list[str | None] = []
    for i, m in enumerate(metas):
        if m["cat"] in CONTENT_CATS:
            theme = content_theme.get(i, -1)
            raw.append(theme_labels[theme] if theme >= 0 else None)
        else:
            raw.append(project_from_path(m.get("path", "")))
    counts = Counter(p for p in raw if p)
    established = {p for p, n in counts.items() if n >= min_size}
    normalized = [normalize_slug(p, established) if p else None for p in raw]
    final_counts = Counter(p for p in normalized if p)
    return [
        p if p and final_counts[p] >= min_size else OTHER for p in normalized
    ]


def index_domains(labels: list[str]) -> tuple[list[int], list[dict]]:
    """Stable indexing: domains ordered by count descending, ties broken by
    first occurrence. Returns (per-point index, domain meta)."""
    counts = Counter(labels)
    ordered = [label for label, _ in counts.most_common()]
    index = {label: i for i, label in enumerate(ordered)}
    meta = [{"label": label, "n": counts[label]} for label in ordered]
    return [index[label] for label in labels], meta
