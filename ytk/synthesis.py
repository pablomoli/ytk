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
        note_word = "note" if len(idxs) == 1 else "notes"
        lines = [f"Cluster {c} ({len(idxs)} {note_word}):"]
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


_PROFILE_SYSTEM = """\
You are building a portrait of a specific person from the content they save and \
study. You will receive their saved items grouped into clusters by semantic \
similarity.

Return JSON matching the schema.

themes
  One entry per cluster you are shown. Use the exact cluster_index given. Give \
each a short human label (2-4 words, e.g. "GPU & creative coding", "personal \
finance") and a one-sentence summary of what ties the cluster together and what \
it says about the person's interest in it.

profile_markdown
  A warm, specific, second-person portrait ("You are...") of 150-300 words. Name \
concrete recurring interests, tools, and themes you see across the clusters. Call \
out what they seem most drawn to, any throughline connecting disparate clusters, \
and what is conspicuously emerging. Be specific and grounded in the items shown — \
never generic. Do not list the clusters mechanically; synthesize.\
"""

_PROFILE_SCHEMA = ProfileSynthesis.model_json_schema()


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
        note_word = "note" if len(t.note_ids) == 1 else "notes"
        lines.append(f"### {t.label} ({pct}% · {len(t.note_ids)} {note_word})")
        lines.append("")
        lines.append(t.summary.strip())
        lines.append("")
    return "\n".join(lines)


def _write_profile_note(snapshot: InterestSnapshot) -> Path:
    """Write the rendered profile to second-brain/me/profile.md, creating dirs."""
    me_dir = _get_brain_path() / "me"
    me_dir.mkdir(parents=True, exist_ok=True)
    path = me_dir / "profile.md"
    path.write_text(render_profile_markdown(snapshot), encoding="utf-8")
    return path


def run_profile(min_notes: int = 5) -> tuple[InterestSnapshot, Path]:
    """Gather -> cluster -> synthesize -> persist. Returns (snapshot, profile_path).

    Raises SynthesisTooSparse if the vault has fewer than min_notes notes.
    """
    cfg = load_config()
    notes = get_all_videos()
    if len(notes) < min_notes:
        raise SynthesisTooSparse(len(notes), min_notes)

    embeddings = np.array([n["embedding"] for n in notes], dtype=float)
    k = choose_k(len(notes), cfg.interest)
    labels = cluster_embeddings(embeddings, k)

    prompt = build_synthesis_prompt(notes, labels)
    data = run_structured(_PROFILE_SYSTEM, prompt, _PROFILE_SCHEMA)
    synthesis = ProfileSynthesis.model_validate(data)

    now = datetime.now(timezone.utc)
    snapshot = assemble_snapshot(notes, labels, synthesis, now.isoformat())
    save_snapshot(snapshot, now.strftime("%Y%m%dT%H%M%SZ"))
    profile_path = _write_profile_note(snapshot)
    return snapshot, profile_path
