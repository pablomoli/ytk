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
from xml.sax.saxutils import escape, quoteattr

import numpy as np
from pydantic import BaseModel
from sklearn.cluster import KMeans

from .config import InterestConfig, load_config
from .interest import (
    ExplicitChannel,
    InterestSnapshot,
    SnapshotDiff,
    Theme,
    ThemeMatch,
    load_latest,
    save_snapshot,
)
from .sdk import run_structured
from .store import get_all_videos, get_content_memories
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
    """Assign each embedding row to one of k clusters. Deterministic (seeded).

    The partition is deliberately UNWEIGHTED. Signal weights (w = 1 + alpha*r)
    used to be passed as sample_weight, and with alpha=7 eleven thought-carrying
    notes carried 55% of the mass — under the v2 encoder that collapsed KMeans
    into two blobs plus singletons (measured 2026-07-17: sizes [90,16,2,1...]
    weighted vs [29,22,19,15,11,11,9,8] unweighted, silhouette 0.013 vs 0.058).
    "Thoughts count more" lives on in theme weight and weighted_centroid, which
    still consume the alpha weights — importance accounting, not geometry.
    """
    km = KMeans(n_clusters=k, random_state=0, n_init=10)
    return [int(label) for label in km.fit_predict(embeddings)]


def weighted_centroid(embeddings: np.ndarray, weights: list[float]) -> list[float]:
    """Confidence-weighted mean embedding, L2-normalized (cosine space)."""
    w = np.asarray(weights, dtype=float)[:, None]
    c = (embeddings * w).sum(axis=0) / w.sum()
    norm = np.linalg.norm(c)
    return list(c / norm if norm else c)


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
            label = f"{n['title']} — {n['thesis']}" if n.get("title") else n["thesis"]
            lines.append(f"  - {label} [tags: {tags}]")
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
    embeddings: np.ndarray | None = None,
    weights: list[float] | None = None,
    levels: list[int] | None = None,
    alpha: float | None = None,
    explicit_min: int = 5,
) -> InterestSnapshot:
    """Combine clustering (authoritative note->theme mapping) with the LLM labels.

    Clustering determines which note belongs to which theme; the LLM only supplies
    the human-readable label and summary per cluster_index. Themes are sorted by
    weight (share of notes) descending.

    v2: when embeddings/weights are given, each theme also stores its
    confidence-weighted centroid (the profile's per-theme query vectors), theme
    weight becomes signal-weighted share, and thought-carrying items (r >= 2)
    form the explicit channel once at least ``explicit_min`` of them exist.
    """
    n = len(notes)
    label_by_index = {t.cluster_index: t for t in synthesis.themes}
    total_w = sum(weights) if weights else n
    themes: list[Theme] = []
    for c, idxs in sorted(_group_by_cluster(labels).items()):
        tl = label_by_index.get(c)
        label = tl.label if tl else f"Theme {c}"
        summary = tl.summary if tl else ""
        cluster_w = sum(weights[i] for i in idxs) if weights else len(idxs)
        themes.append(Theme(
            id=_slug(label),
            label=label,
            summary=summary,
            weight=round(cluster_w / total_w, 4),
            note_ids=[notes[i]["id"] for i in idxs],
            exemplar_titles=[notes[i]["title"] for i in idxs[:3]],
            centroid=weighted_centroid(embeddings[idxs], [weights[i] for i in idxs])
            if embeddings is not None and weights else None,
        ))
    themes.sort(key=lambda t: t.weight, reverse=True)

    explicit = None
    if embeddings is not None and levels:
        exp_idx = [i for i, r in enumerate(levels) if r >= 2]
        if len(exp_idx) >= explicit_min:
            explicit = ExplicitChannel(
                note_ids=[notes[i]["id"] for i in exp_idx],
                exemplar_titles=[notes[i]["title"] for i in exp_idx[:5]],
                centroid=weighted_centroid(embeddings[exp_idx], [1.0] * len(exp_idx)),
            )

    from collections import Counter

    return InterestSnapshot(
        generated_at=generated_at,
        note_count=n,
        themes=themes,
        connections=[],
        profile_markdown=synthesis.profile_markdown,
        alpha=alpha,
        signal_counts=dict(Counter(levels)) if levels else {},
        explicit=explicit,
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


def render_profile(snapshot: InterestSnapshot) -> str:
    """Render a snapshot to second-brain/me/profile.md as an AI-traversable document.

    The body is XML rather than prose-Markdown so an agent can walk the profile
    structurally: themes carry their rank, weight, share and note count as
    attributes and list concrete exemplar titles, while the synthesized portrait
    is preserved verbatim inside <portrait>. YAML frontmatter is kept so the note
    still behaves like a normal Obsidian file.
    """
    lines = [
        "---",
        "type: interest-profile",
        f"generated: {snapshot.generated_at}",
        f"notes: {snapshot.note_count}",
        "---",
        "",
        f"<interest-profile generated={quoteattr(snapshot.generated_at)} "
        f"notes=\"{snapshot.note_count}\" themes=\"{len(snapshot.themes)}\">",
        "  <portrait>",
        _indent(escape(snapshot.profile_markdown.strip()), 4),
        "  </portrait>",
        "  <themes>",
    ]
    for rank, t in enumerate(snapshot.themes, start=1):
        pct = round(t.weight * 100)
        lines.append(
            f"    <theme rank=\"{rank}\" id={quoteattr(t.id)} "
            f"weight=\"{t.weight}\" share=\"{pct}%\" notes=\"{len(t.note_ids)}\">"
        )
        lines.append(f"      <label>{escape(t.label)}</label>")
        lines.append(f"      <summary>{escape(t.summary.strip())}</summary>")
        exemplars = [e.strip() for e in t.exemplar_titles if e.strip()]
        if exemplars:
            lines.append("      <exemplars>")
            for e in exemplars:
                lines.append(f"        <exemplar>{escape(e)}</exemplar>")
            lines.append("      </exemplars>")
        lines.append("    </theme>")
    lines.append("  </themes>")
    lines.append("</interest-profile>")
    lines.append("")
    return "\n".join(lines)


def _indent(text: str, spaces: int) -> str:
    """Indent every line of ``text`` by ``spaces``, leaving blank lines empty."""
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.splitlines())


def _embeddings_by_id() -> dict[str, list[float]]:
    """Current embedding for every profile-eligible record, keyed by id."""
    cfg = load_config()
    return {n["id"]: n["embedding"]
            for n in get_all_videos() + get_content_memories(cfg.interest.content_sources)
            if n.get("embedding")}


def _theme_centroids(snapshot: InterestSnapshot, emb_by_id: dict | None = None) -> list[np.ndarray | None]:
    """Centroid per theme, backfilling pre-v2 snapshots from note_ids.

    Backfill uses the CURRENT embedder for old snapshots — required anyway,
    since cross-snapshot cosine only means something in one embedding space
    (the vault re-embedded MiniLM -> gte-small on 2026-07-05).
    """
    out: list[np.ndarray | None] = []
    for t in snapshot.themes:
        if t.centroid:
            out.append(np.asarray(t.centroid, dtype=float))
            continue
        if emb_by_id is None:
            emb_by_id = _embeddings_by_id()
        vecs = [emb_by_id[i] for i in t.note_ids if i in emb_by_id]
        if not vecs:
            out.append(None)
            continue
        c = np.asarray(vecs, dtype=float).mean(axis=0)
        n = np.linalg.norm(c)
        out.append(c / n if n else c)
    return out


def diff_snapshots(old: InterestSnapshot, new: InterestSnapshot, floor: float = 0.75) -> SnapshotDiff:
    """Match themes across two runs by centroid cosine; the rest is drift.

    Greedy one-to-one matching, highest similarity first, cut off at ``floor``
    so a genuinely new theme is never force-married to a fading old one.
    Unmatched new themes are births; unmatched old ones are deaths.
    """
    emb_by_id = _embeddings_by_id()
    oc = _theme_centroids(old, emb_by_id)
    nc = _theme_centroids(new, emb_by_id)
    pairs = []
    for i, a in enumerate(oc):
        for j, b in enumerate(nc):
            if a is not None and b is not None:
                pairs.append((float(a @ b), i, j))
    pairs.sort(reverse=True)

    used_old: set[int] = set()
    used_new: set[int] = set()
    matched: list[ThemeMatch] = []
    for sim, i, j in pairs:
        if sim < floor or i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new.add(j)
        matched.append(ThemeMatch(
            old_label=old.themes[i].label, new_label=new.themes[j].label,
            old_weight=old.themes[i].weight, new_weight=new.themes[j].weight,
            similarity=round(sim, 3),
        ))
    return SnapshotDiff(
        old_generated_at=old.generated_at,
        new_generated_at=new.generated_at,
        matched=matched,
        born=[t.label for j, t in enumerate(new.themes) if j not in used_new],
        died=[t.label for i, t in enumerate(old.themes) if i not in used_old],
    )


def render_drift(diff: SnapshotDiff) -> str:
    """Markdown drift section for profile.md: births, deaths, biggest movers."""
    lines = [f"\n## Taste drift (since {diff.old_generated_at[:10]})\n"]
    for label in diff.born:
        lines.append(f"- **emerging:** {label}")
    for label in diff.died:
        lines.append(f"- **faded out:** {label}")
    movers = sorted(diff.matched, key=lambda m: abs(m.new_weight - m.old_weight), reverse=True)
    for m in movers[:5]:
        d = m.new_weight - m.old_weight
        if abs(d) < 0.01:
            continue
        arrow = "growing" if d > 0 else "fading"
        name = m.new_label if m.new_label == m.old_label else f"{m.old_label} -> {m.new_label}"
        lines.append(f"- **{arrow}:** {name} ({m.old_weight:.0%} -> {m.new_weight:.0%})")
    if len(lines) == 1:
        lines.append("- stable: no meaningful movement between runs")
    return "\n".join(lines) + "\n"


def _write_profile_note(snapshot: InterestSnapshot) -> Path:
    """Write the rendered profile to second-brain/me/profile.md, creating dirs."""
    me_dir = _get_brain_path() / "me"
    me_dir.mkdir(parents=True, exist_ok=True)
    path = me_dir / "profile.md"
    path.write_text(render_profile(snapshot), encoding="utf-8")
    return path


def run_profile(min_notes: int = 5) -> tuple[InterestSnapshot, Path]:
    """Gather -> cluster -> synthesize -> persist. Returns (snapshot, profile_path).

    Gathers YouTube videos plus the ingested "media-diet" memory docs (reels,
    TikToks, articles) named in cfg.interest.content_sources, so the profile
    reflects all consumed content rather than YouTube alone. Notes without
    embeddings are filtered out before clustering so a malformed record cannot
    cause a ragged-array ValueError in KMeans. The min_notes sparse check runs
    against this filtered set, so a vault of embedding-less records is correctly
    reported as sparse rather than crashing.

    Raises SynthesisTooSparse if fewer than min_notes embeddable notes exist.
    """
    cfg = load_config()
    gathered = get_all_videos() + get_content_memories(cfg.interest.content_sources)
    notes = [n for n in gathered if n.get("embedding")]
    if len(notes) < min_notes:
        raise SynthesisTooSparse(len(notes), min_notes)

    from . import signals

    embeddings = np.array([n["embedding"] for n in notes], dtype=float)
    levels = signals.signal_levels(notes)
    weights = signals.weights(levels, cfg.interest.alpha)
    k = choose_k(len(notes), cfg.interest)
    labels = cluster_embeddings(embeddings, k)

    prompt = build_synthesis_prompt(notes, labels)
    data = run_structured(_PROFILE_SYSTEM, prompt, _PROFILE_SCHEMA)
    synthesis = ProfileSynthesis.model_validate(data)

    now = datetime.now(timezone.utc)
    snapshot = assemble_snapshot(
        notes, labels, synthesis, now.isoformat(),
        embeddings=embeddings, weights=weights, levels=levels,
        alpha=cfg.interest.alpha, explicit_min=cfg.interest.explicit_min,
    )
    previous = load_latest()
    save_snapshot(snapshot, now.strftime("%Y%m%dT%H%M%SZ"))
    profile_path = _write_profile_note(snapshot)
    if previous is not None:
        try:
            drift = render_drift(diff_snapshots(previous, snapshot))
            profile_path.write_text(
                profile_path.read_text(encoding="utf-8") + drift, encoding="utf-8"
            )
        except Exception:
            pass  # drift is a bonus; it must never fail a profile run
    return snapshot, profile_path


def rerender_latest() -> tuple[InterestSnapshot, Path]:
    """Rewrite profile.md from the most recent snapshot without a Claude call.

    Used by ``ytk profile --render-only`` to refresh the note's format after a
    renderer change, with no clustering or API cost. Raises FileNotFoundError if
    no snapshot has been synthesized yet.
    """
    snapshot = load_latest()
    if snapshot is None:
        raise FileNotFoundError("no interest snapshot found; run `ytk profile` first")
    return snapshot, _write_profile_note(snapshot)
