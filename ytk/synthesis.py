# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Synthesis engine for ytk's interest model.

Reads every note's embedding + enrichment from the ChromaDB video collection,
clusters notes into themes, and makes one Claude structured call to label the
clusters and write a prose profile. Pure helpers are unit-tested; `run_profile`
wires the store and the Claude SDK together.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import numpy as np
from pydantic import BaseModel
from sklearn.cluster import KMeans

from .config import InterestConfig, load_config
from .interest import (
    ExplicitChannel,
    InterestSnapshot,
    PortraitClaim,
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
    # n_init: sklearn's stub says str, the runtime takes an int.
    km = KMeans(n_clusters=k, random_state=0, n_init=10)  # type: ignore[reportArgumentType]
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
    evidence_ids: list[str]


class PortraitClaimOutput(BaseModel):
    """One portrait paragraph and the exact vault evidence behind it.

    The paragraph is the auditable claim unit: the portrait reads as a flowing
    second-person essay, but every paragraph still carries machine-readable
    evidence refs so #94's checker can audit what grounds it.
    """

    text: str
    evidence_ids: list[str]


class ProfileSynthesis(BaseModel):
    """Full structured output returned by the synthesis Claude call."""

    themes: list[ThemeLabel]
    claims: list[PortraitClaimOutput]


class ProfileGroundingError(ValueError):
    """Structured synthesis cited missing, mismatched, or stale evidence."""


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


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def evidence_is_fresh(captured_at: str, generated_at: str, half_life_days: float) -> bool:
    """Whether capture time is known and no older than one decay half-life."""
    captured = _parse_timestamp(captured_at)
    generated = _parse_timestamp(generated_at)
    if captured is None or generated is None:
        return False
    age_days = max(0.0, (generated - captured).total_seconds() / 86400)
    return age_days <= half_life_days


def build_synthesis_prompt(
    notes: list[dict],
    labels: list[int],
    generated_at: str | None = None,
    half_life_days: float = 90.0,
    levels: list[int] | None = None,
    previous_portrait: str | None = None,
) -> str:
    """Render the clustered notes into a compact prompt for the synthesis call."""
    generated_at = generated_at or datetime.now(UTC).isoformat()
    if levels is None:
        levels = [0] * len(notes)
    if len(levels) != len(notes):
        raise ValueError("levels and notes must have matching lengths")
    signal_names = {
        0: "passive exposure",
        1: "deliberate save",
        2: "authored thought",
        3: "authored directive",
    }
    blocks: list[str] = []
    for c, idxs in sorted(_group_by_cluster(labels).items()):
        note_word = "note" if len(idxs) == 1 else "notes"
        lines = [f"Cluster {c} ({len(idxs)} {note_word}):"]
        # Newest first so the model reads a cluster's present before its past;
        # store insertion order used to head every list with the oldest items,
        # and lazy evidence selection mirrored whatever came first.
        for i in sorted(idxs, key=lambda i: notes[i].get("captured_at", ""), reverse=True):
            n = notes[i]
            tags = ", ".join(n["tags"])
            label = f"{n['title']} — {n['thesis']}" if n.get("title") else n["thesis"]
            captured = n.get("captured_at") or "unknown"
            citable = (
                "yes"
                if evidence_is_fresh(n.get("captured_at", ""), generated_at, half_life_days)
                else "no"
            )
            lines.append(
                f"  - [{n['id']}] {label} "
                f"[tags: {tags}; captured: {captured}; citable: {citable}; "
                f"signal: r={levels[i]} {signal_names.get(levels[i], 'unknown')}]"
            )
        blocks.append("\n".join(lines))
    prompt = (
        "Below are clusters of the user's saved content (videos, reels, TikToks, "
        "articles), grouped by semantic similarity. Each line is one saved item: "
        "[exact item id] title — thesis [tags; capture time; whether it is fresh "
        "enough to cite; capture signal]. Items are listed newest-capture first. "
        "Signal meaning: r=0 is passive exposure, "
        "r=1 is a deliberate save, r=2 is a user-authored thought, and r=3 is an "
        f"authored directive. The evidence half-life is {half_life_days:g} days.\n\n"
        + "\n\n".join(blocks)
    )
    if previous_portrait and previous_portrait.strip():
        prompt += "\n\nPrevious portrait (evolve, do not rewrite):\n" + previous_portrait.strip()
    return prompt


def _require_grounded(
    what: str,
    evidence_ids: list[str],
    allowed_ids: set[str],
    fresh_ids: set[str] | None = None,
) -> None:
    """Evidence refs must exist and stay inside the allowed id set.

    ``fresh_ids`` gates freshness only when given. Portrait claims pass it —
    #94's bias check says no claim survives on empty or stale-only evidence.
    Theme summaries do NOT: they are full-history category descriptions, and a
    category whose notes lack capture timestamps is still a real category.
    """
    if not evidence_ids:
        raise ProfileGroundingError(f"{what} has no evidence")
    unknown = set(evidence_ids) - allowed_ids
    if unknown:
        raise ProfileGroundingError(
            f"{what} cites evidence outside its allowed set: {sorted(unknown)}"
        )
    if fresh_ids is not None and not set(evidence_ids) & fresh_ids:
        raise ProfileGroundingError(f"{what} has no evidence captured within the decay half-life")


def _exemplar_indices(
    embeddings: np.ndarray | None,
    idxs: list[int],
    centroid: list[float] | None,
    n: int = 3,
) -> list[int]:
    """The cluster members nearest the theme centroid.

    Representative exemplars, not the first rows in store insertion order —
    insertion order made every theme showcase the oldest videos ever added.
    Falls back to the first ``n`` members for v1 calls without embeddings.
    """
    if embeddings is None or centroid is None:
        return idxs[:n]
    sub = np.asarray(embeddings[idxs], dtype=float)
    norms = np.maximum(np.linalg.norm(sub, axis=1), 1e-12)
    sims = (sub / norms[:, None]) @ np.asarray(centroid, dtype=float)
    return [idxs[i] for i in np.argsort(-sims)[:n]]


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
    decay_half_life_days: float = 90.0,
    fresh_window_days: float | None = None,
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
    grouped = _group_by_cluster(labels)
    all_ids = {n["id"] for n in notes}
    signal_by_id = {notes[i]["id"]: (levels[i] if levels else 0) for i in range(n)}
    fresh_ids = {
        item["id"]
        for item in notes
        if evidence_is_fresh(item.get("captured_at", ""), generated_at, decay_half_life_days)
    }
    # Claim grounding stays on the half-life (fresh_ids); the overlay gets its
    # own shorter window, else a corpus younger than the half-life paints ~100%
    # of every theme "recent" and the two-tone bars carry nothing.
    overlay_ids = (
        fresh_ids
        if fresh_window_days is None
        else {
            item["id"]
            for item in notes
            if evidence_is_fresh(item.get("captured_at", ""), generated_at, fresh_window_days)
        }
    )
    for c, idxs in grouped.items():
        tl = label_by_index.get(c)
        if tl is None:
            raise ProfileGroundingError(f"cluster {c} has no synthesized theme")
        cluster_ids = {notes[i]["id"] for i in idxs}
        # No freshness gate here: themes are full-history categories and must
        # survive clusters whose notes all lack capture timestamps.
        _require_grounded(f"theme {c} summary", tl.evidence_ids, cluster_ids)
    if not synthesis.claims:
        raise ProfileGroundingError("portrait has no claims")
    for i, claim in enumerate(synthesis.claims, start=1):
        _require_grounded(f"portrait claim {i}", claim.evidence_ids, all_ids, fresh_ids)

    total_w = sum(weights) if weights else n
    themes: list[Theme] = []
    for c, idxs in sorted(grouped.items()):
        tl = label_by_index.get(c)
        label = tl.label if tl else f"Theme {c}"
        summary = tl.summary if tl else ""
        cluster_w = sum(weights[i] for i in idxs) if weights else len(idxs)
        centroid = (
            weighted_centroid(embeddings[idxs], [weights[i] for i in idxs])
            if embeddings is not None and weights
            else None
        )
        exemplar_idx = _exemplar_indices(
            embeddings,
            # Prefer titled notes: an untitled memory doc may be the closest
            # member but makes a blank exemplar row.
            [i for i in idxs if notes[i]["title"].strip()] or idxs,
            centroid,
        )
        themes.append(
            Theme(
                id=_slug(label),
                label=label,
                summary=summary,
                weight=round(cluster_w / total_w, 4),
                note_ids=[notes[i]["id"] for i in idxs],
                exemplar_titles=[notes[i]["title"] for i in exemplar_idx],
                exemplar_sources=[notes[i].get("source", "") for i in exemplar_idx],
                evidence_ids=tl.evidence_ids if tl else [],
                fresh_note_count=sum(1 for i in idxs if notes[i]["id"] in overlay_ids),
                centroid=centroid,
            )
        )
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

    cited_ids = {
        evidence_id for claim in synthesis.claims for evidence_id in claim.evidence_ids
    } | {evidence_id for theme in synthesis.themes for evidence_id in theme.evidence_ids}
    return InterestSnapshot(
        generated_at=generated_at,
        note_count=n,
        themes=themes,
        connections=[],
        profile_markdown="\n\n".join(c.text.strip() for c in synthesis.claims),
        portrait_claims=[
            PortraitClaim(text=c.text.strip(), evidence_ids=c.evidence_ids)
            for c in synthesis.claims
        ],
        evidence_captured_at={
            item["id"]: item.get("captured_at", "") for item in notes if item["id"] in cited_ids
        },
        evidence_signals={item_id: signal_by_id.get(item_id, 0) for item_id in sorted(cited_ids)},
        alpha=alpha,
        decay_half_life_days=decay_half_life_days,
        signal_counts=dict(Counter(levels)) if levels else {},
        explicit=explicit,
    )


_PROFILE_SYSTEM = """\
You are writing the interest profile of one specific person from everything \
they have captured (videos, reels, TikToks, articles): a concrete category \
label per cluster, and a portrait that tells them something true and specific \
about themselves.

Signal levels calibrate language. r=0 (passively synced) shows what recurs in \
their stream; r=1 (deliberate save) shows what they chose to keep; r=2/r=3 \
(authored thought/directive) shows what they engaged with in their own words. \
Describe attraction, attention, and pursuit — "you keep returning to", "you \
study", "you're drawn to" — never mastery: no claims of expertise, skill \
level, or accomplishment at any signal level.

Return JSON matching the schema.

themes
  One entry per cluster, using the exact cluster_index given. label: a concrete \
noun-phrase category of 2-4 words naming the subject matter (e.g. "agentic AI \
coding craft", "GPU & creative coding", "personal finance") — a scannable \
category, not a metaphor or motif. summary: one factual sentence stating the \
pattern that ties the cluster's notes together, scoped to the notes and naming \
concrete tools, techniques, or topics; no second-person voice, no implied \
mastery. evidence_ids: 1-4 exact item ids from that same cluster that best \
represent the pattern.

claims
  The portrait: 3-5 short paragraphs, 100-220 words total, written to the \
person in second person. It describes the PERSON, not the media: the shape of \
their attention, the moves they keep making, the appetites connecting \
disparate clusters, and what is strengthening or fading. Write at the level of \
"you want the aesthetic, the schematic, and the physical build all at once" or \
"your throughline is mechanism: something opaque reframed as an intelligible, \
buildable system" — abstract, dispositional, earned from the whole corpus and \
its full time span. NEVER name a tool, product, technology, person, title, or \
technical concept from the items; the concrete inventory lives in the theme \
categories, and the portrait is read as a time series where such particulars \
break comparability. Captured items prove attraction, not action or knowledge: \
say "drawn to", "keep returning to", "collecting" — never "you build", "you \
use", "you study X" for things merely captured, and never imply familiarity \
with material that was only queued. Do not describe the capture system itself \
as a trait. Avoid therapy language, horoscope vagueness, and flattery. Each \
paragraph is one claim entry: its evidence_ids hold 2-6 exact item ids whose \
pattern the paragraph abstracts, at least one marked citable: yes, drawn from \
across the time span rather than one capture batch. Never invent an id or \
cite one the paragraph does not rely on. When newer evidence contradicts \
older, follow the newer; do not accumulate stale traits.\
"""

_PROFILE_CONTINUITY = """\


A previous portrait of this person is included below. Evolve it rather than \
rewriting from scratch: carry forward the dispositions the evidence still \
supports, adjust emphasis where the evidence changed, and add only what is \
genuinely new. If the previous portrait names tools, items, or concepts, \
abstract them into the disposition they evidence — do not carry the names \
forward. The person should recognize themselves between runs.\
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
    score_attr = (
        f' profile-score="{snapshot.profile_score.score:.4f}"' if snapshot.profile_score else ""
    )
    half_life = snapshot.decay_half_life_days or 90.0
    lines = [
        "---",
        "type: interest-profile",
        f"generated: {snapshot.generated_at}",
        f"notes: {snapshot.note_count}",
        "---",
        "",
        f"<interest-profile generated={quoteattr(snapshot.generated_at)} "
        f'notes="{snapshot.note_count}" themes="{len(snapshot.themes)}" '
        f'evidence-half-life-days="{half_life:g}"{score_attr}>',
        "  <portrait>",
    ]
    if snapshot.portrait_claims:
        for claim in snapshot.portrait_claims:
            evidence = " ".join(claim.evidence_ids)
            lines.append(
                f"    <claim evidence={quoteattr(evidence)}>{escape(claim.text.strip())}</claim>"
            )
    elif snapshot.profile_markdown.strip():
        # Old snapshots remain renderable, but the checker intentionally fails
        # this legacy form because it has no auditable evidence references.
        lines.append(f"    <claim>{escape(snapshot.profile_markdown.strip())}</claim>")
    lines.extend(["  </portrait>", "  <themes>"])
    for rank, t in enumerate(snapshot.themes, start=1):
        pct = round(t.weight * 100)
        lines.append(
            f'    <theme rank="{rank}" id={quoteattr(t.id)} '
            f'weight="{t.weight}" share="{pct}%" notes="{len(t.note_ids)}" '
            f'fresh-notes="{t.fresh_note_count}">'
        )
        lines.append(f"      <label>{escape(t.label)}</label>")
        evidence = " ".join(t.evidence_ids)
        lines.append(
            f"      <summary evidence={quoteattr(evidence)}>{escape(t.summary.strip())}</summary>"
        )
        exemplars = [e.strip() for e in t.exemplar_titles if e.strip()]
        if exemplars:
            lines.append("      <exemplars>")
            for e in exemplars:
                lines.append(f"        <exemplar>{escape(e)}</exemplar>")
            lines.append("      </exemplars>")
        lines.append("    </theme>")
    lines.append("  </themes>")
    lines.append("  <evidence-catalog>")
    for evidence_id, captured_at in sorted(snapshot.evidence_captured_at.items()):
        signal = snapshot.evidence_signals.get(evidence_id, 0)
        lines.append(
            f"    <evidence id={quoteattr(evidence_id)} "
            f'captured-at={quoteattr(captured_at)} signal="{signal}" />'
        )
    lines.append("  </evidence-catalog>")
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
    return {
        n["id"]: n["embedding"]
        for n in get_all_videos() + get_content_memories(cfg.interest.content_sources)
        if n.get("embedding")
    }


def _theme_centroids(
    snapshot: InterestSnapshot, emb_by_id: dict | None = None
) -> list[np.ndarray | None]:
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


def diff_snapshots(
    old: InterestSnapshot, new: InterestSnapshot, floor: float = 0.75
) -> SnapshotDiff:
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
        matched.append(
            ThemeMatch(
                old_label=old.themes[i].label,
                new_label=new.themes[j].label,
                old_weight=old.themes[i].weight,
                new_weight=new.themes[j].weight,
                similarity=round(sim, 3),
            )
        )
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


def notes_since_snapshot() -> tuple[int, InterestSnapshot | None]:
    """Return (embeddable-note delta vs the latest snapshot, that snapshot).

    Delta is a plain count difference, not a captured_at comparison: timestamp
    coverage is uneven across sources, so a date filter would undercount.
    """
    cfg = load_config()
    gathered = get_all_videos() + get_content_memories(cfg.interest.content_sources)
    current = sum(1 for n in gathered if n.get("embedding"))
    previous = load_latest()
    if previous is None:
        return current, None
    return current - previous.note_count, previous


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

    now = datetime.now(UTC)
    embeddings = np.array([n["embedding"] for n in notes], dtype=float)
    levels = signals.signal_levels(notes)
    # Weights use the intake-adjusted levels (E4: raw r re-ranks themes by
    # capture medium); prompt, signal_counts and explicit channel keep raw r.
    weight_levels = (
        signals.intake_adjusted_levels(levels, [n["source"] for n in notes])
        if cfg.interest.medium_controlled
        else levels
    )
    weights = signals.decayed_weights(
        weight_levels,
        [n.get("captured_at", "") for n in notes],
        cfg.interest.alpha,
        cfg.interest.decay_half_life_days,
        now,
    )
    # Taxonomy dimensionality depends only on corpus size, never on timestamp
    # coverage: freshness is reported per theme (fresh_note_count), it does not
    # merge or erase categories (#94 post-review correction).
    k = choose_k(len(notes), cfg.interest)
    labels = cluster_embeddings(embeddings, k)

    previous = load_latest()
    prompt = build_synthesis_prompt(
        notes,
        labels,
        now.isoformat(),
        cfg.interest.decay_half_life_days,
        levels,
        previous_portrait=previous.profile_markdown if previous else None,
    )
    system = _PROFILE_SYSTEM + (_PROFILE_CONTINUITY if previous else "")
    # One feedback retry: with hundreds of long ids the model occasionally
    # cites an id from a neighboring cluster; the grounding gate catches it,
    # and a second attempt with the exact rejection usually lands.
    snapshot = None
    grounding_error: ProfileGroundingError | None = None
    for _ in range(2):
        attempt_prompt = (
            prompt
            if grounding_error is None
            else (
                f"{prompt}\n\nYour previous attempt was rejected by a validator: "
                f"{grounding_error}. Cite only exact ids listed in the relevant "
                "cluster."
            )
        )
        data = run_structured(system, attempt_prompt, _PROFILE_SCHEMA)
        synthesis = ProfileSynthesis.model_validate(data)
        try:
            snapshot = assemble_snapshot(
                notes,
                labels,
                synthesis,
                now.isoformat(),
                embeddings=embeddings,
                weights=weights,
                levels=levels,
                alpha=cfg.interest.alpha,
                explicit_min=cfg.interest.explicit_min,
                decay_half_life_days=cfg.interest.decay_half_life_days,
                fresh_window_days=cfg.interest.fresh_window_days,
            )
            break
        except ProfileGroundingError as exc:
            grounding_error = exc
    if snapshot is None:
        # grounding_error is only set by a failed attempt; with no attempts at
        # all `raise None` would mask the real problem behind a TypeError.
        raise grounding_error or ProfileGroundingError(
            "profile synthesis produced no snapshot and no grounding error"
        )
    from .profile_eval import ProfileEvaluationUnavailable, evaluate_snapshot
    from .store import _TEXT_MODEL

    snapshot.embedding_model = _TEXT_MODEL
    snapshot.profile_score = evaluate_snapshot(snapshot, notes, levels, cfg.interest, previous)
    if snapshot.profile_score is None:
        raise ProfileEvaluationUnavailable(
            "no evidence-disjoint saved/pending visual cohort; run "
            "`ytk visual index` and sync the discovery queue before regenerating"
        )
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
