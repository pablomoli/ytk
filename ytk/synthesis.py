"""Synthesis engine for ytk's interest model.

Reads every note's embedding + enrichment from the ChromaDB video collection,
clusters notes into themes, and makes one Claude structured call to label the
clusters and write a prose profile. Pure helpers are unit-tested; `run_profile`
wires the store and the Claude SDK together.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pydantic import BaseModel
from sklearn.cluster import KMeans

from .config import InterestConfig, load_config
from .interest import InterestSnapshot, Theme, save_snapshot
from .sdk import run_structured
from .store import get_all_videos
from .vault import _get_brain_path


class SynthesisTooSparse(Exception):
    """Raised when the vault has too few notes to synthesize a profile."""

    def __init__(self, have: int, need: int):
        super().__init__(f"need at least {need} notes to synthesize, have {have}")
        self.have = have
        self.need = need


def choose_k(n: int, cfg: InterestConfig) -> int:
    """Pick a cluster count: sqrt-scaled, clamped to [cluster_min, cluster_max] and n."""
    if n <= 0:
        return 1
    if n <= cfg.cluster_min:
        return n
    k = round(math.sqrt(n / 2))
    return max(cfg.cluster_min, min(cfg.cluster_max, k, n))


def cluster_embeddings(embeddings: np.ndarray, k: int) -> list[int]:
    """Assign each embedding row to one of k clusters. Deterministic (seeded)."""
    km = KMeans(n_clusters=k, random_state=0, n_init=10)
    return [int(label) for label in km.fit_predict(embeddings)]


class ThemeLabel(BaseModel):
    """LLM-supplied label and summary for a single cluster."""

    cluster_index: int
    label: str
    summary: str


class ProfileSynthesis(BaseModel):
    """Full structured output returned by the synthesis Claude call."""

    themes: list[ThemeLabel]
    profile_markdown: str


def _slug(label: str) -> str:
    """Lowercase, hyphenate, strip non-alphanumerics for a stable theme id."""
    s = re.sub(r"[^a-z0-9]+", "-", label.lower())
    return s.strip("-")


def _group_by_cluster(labels: list[int]) -> dict[int, list[int]]:
    """Return a mapping of cluster index -> list of note positions."""
    clusters: dict[int, list[int]] = {}
    for idx, c in enumerate(labels):
        clusters.setdefault(int(c), []).append(idx)
    return clusters


def build_synthesis_prompt(notes: list[dict], labels: list[int]) -> str:
    """Render the clustered notes into a compact prompt for the synthesis call."""
    blocks: list[str] = []
    for c, idxs in sorted(_group_by_cluster(labels).items()):
        lines = [f"Cluster {c} ({len(idxs)} notes):"]
        for i in idxs:
            n = notes[i]
            tags = ", ".join(n["tags"])
            lines.append(f"  - {n['title']} — {n['thesis']} [tags: {tags}]")
        blocks.append("\n".join(lines))
    return (
        "Below are clusters of the user's saved content (videos, reels, TikToks, "
        "articles), grouped by semantic similarity. Each line is one saved item: "
        "title — thesis [tags].\n\n" + "\n\n".join(blocks)
    )


def assemble_snapshot(
    notes: list[dict],
    labels: list[int],
    synthesis: ProfileSynthesis,
    generated_at: str,
) -> InterestSnapshot:
    """Combine clustering (authoritative note->theme mapping) with the LLM labels.

    Clustering determines which note belongs to which theme; the LLM only supplies
    the human-readable label and summary per cluster_index. Themes are sorted by
    weight (share of notes) descending.
    """
    n = len(notes)
    label_by_index = {t.cluster_index: t for t in synthesis.themes}
    themes: list[Theme] = []
    for c, idxs in sorted(_group_by_cluster(labels).items()):
        tl = label_by_index.get(c)
        label = tl.label if tl else f"Theme {c}"
        summary = tl.summary if tl else ""
        themes.append(Theme(
            id=_slug(label),
            label=label,
            summary=summary,
            weight=round(len(idxs) / n, 4),
            note_ids=[notes[i]["id"] for i in idxs],
            exemplar_titles=[notes[i]["title"] for i in idxs[:3]],
        ))
    themes.sort(key=lambda t: t.weight, reverse=True)
    return InterestSnapshot(
        generated_at=generated_at,
        note_count=n,
        themes=themes,
        connections=[],
        profile_markdown=synthesis.profile_markdown,
    )


def render_profile_markdown(snapshot: InterestSnapshot) -> str:
    """Render a snapshot to the Obsidian note body written to second-brain/me/profile.md."""
    lines = [
        "---",
        "type: interest-profile",
        f"generated: {snapshot.generated_at}",
        f"notes: {snapshot.note_count}",
        "---",
        "",
        "# Interest Profile",
        "",
        snapshot.profile_markdown.strip(),
        "",
        "## Themes",
        "",
    ]
    for t in snapshot.themes:
        pct = round(t.weight * 100)
        lines.append(f"### {t.label}  ({pct}% · {len(t.note_ids)} notes)")
        lines.append("")
        lines.append(t.summary.strip())
        lines.append("")
    return "\n".join(lines)
