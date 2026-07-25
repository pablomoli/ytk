# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Interest-model data types and snapshot persistence for ytk.

A snapshot is the durable artifact the synthesis engine produces: the user's
themes, cross-note connections, and a synthesized prose profile. Later phases
(persona, digest) read these snapshots. Snapshots are written atomically and
versioned by timestamp; `latest.json` always points at the newest run.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class Connection(BaseModel):
    """A weighted link between two themes discovered during synthesis."""

    a: str
    b: str
    why: str
    strength: float


class Theme(BaseModel):
    """A named cluster of notes that share a coherent topic or interest area.

    ``centroid`` (v2) is the theme's weighted mean embedding — one of the
    profile's multiple query vectors. Retrieval goes per-theme then merges;
    never query with a single all-taste centroid.
    """

    id: str
    label: str
    summary: str
    weight: float
    note_ids: list[str]
    exemplar_titles: list[str]
    # Parallel to exemplar_titles: which pipeline each exemplar came from
    # (youtube, instagram, tiktok, ...), so the hub can badge provenance.
    exemplar_sources: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    # Recency overlay: how many of this theme's notes were captured within the
    # decay half-life. Reported, never used to gate or merge themes — the
    # taxonomy is full-history and independent of timestamp coverage.
    fresh_note_count: int = 0
    centroid: list[float] | None = None


class PortraitClaim(BaseModel):
    """One auditable portrait paragraph with its machine-readable evidence."""

    text: str
    evidence_ids: list[str]


class ProfileScore(BaseModel):
    """BUMP-style forward ranking result for one profile regeneration."""

    score: float
    metric: str = "multi-positive-ndcg"
    protocol: str = "bump-forward-evidence-redacted-visual-v1"
    positive_ids: list[str]
    negative_ids: list[str]
    candidate_fingerprint: str
    encoder: str
    claim_count: int
    comparable_to_previous: bool = False
    previous_score: float | None = None
    delta: float | None = None
    warning: str | None = None


class ExplicitChannel(BaseModel):
    """Explicit interests: items the user wrote a thought about (r >= 2).

    A separate retrieval channel (Pinterest: explicit interests retrieve
    almost disjoint content from behavioral clusters). Gated on
    interest.explicit_min members; None in snapshots until the vault has
    enough thought-carrying saves.
    """

    note_ids: list[str]
    exemplar_titles: list[str]
    centroid: list[float]


class InterestSnapshot(BaseModel):
    """Complete output of one interest-model synthesis run.

    Persisted as JSON under ``~/.ytk/interest/``. The ``connections`` field is
    intentionally empty in Phase 0 and populated by later synthesis phases.
    v2 fields record the run's parameters so their evolution across snapshots
    is itself a time series (alpha, signal distribution).
    """

    generated_at: str
    note_count: int
    themes: list[Theme]
    connections: list[Connection] = Field(default_factory=list)
    profile_markdown: str
    portrait_claims: list[PortraitClaim] = Field(default_factory=list)
    evidence_captured_at: dict[str, str] = Field(default_factory=dict)
    evidence_signals: dict[str, int] = Field(default_factory=dict)
    alpha: float | None = None
    decay_half_life_days: float | None = None
    signal_counts: dict[int, int] = Field(default_factory=dict)
    explicit: ExplicitChannel | None = None
    profile_score: ProfileScore | None = None
    # Which encoder produced the centroids. Snapshots re-anchored across an
    # embedding-epoch swap keep themes/weights (taste didn't change) but new
    # centroid geometry; reanchored_from records the source run so the #83
    # time series can mark the epoch boundary instead of faking a taste event.
    embedding_model: str | None = None
    reanchored_from: str | None = None


class ThemeMatch(BaseModel):
    """A theme paired across two snapshots by centroid similarity."""

    old_label: str
    new_label: str
    old_weight: float
    new_weight: float
    similarity: float


class SnapshotDiff(BaseModel):
    """Taste drift between two profile runs (issue #16, E4).

    The research-sanctioned alternative to recency decay: interest evolution
    as discrete cluster birth/death plus weight movement on matched themes.
    """

    old_generated_at: str
    new_generated_at: str
    matched: list[ThemeMatch]
    born: list[str]
    died: list[str]


_INTEREST_DIR = Path.home() / ".ytk" / "interest"


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path via a temp file + rename so a crash never corrupts it."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_snapshot(snapshot: InterestSnapshot, ts_slug: str) -> Path:
    """Persist the snapshot as snapshot-<ts_slug>.json and rewrite latest.json.

    Returns the path to the timestamped file.
    """
    _INTEREST_DIR.mkdir(parents=True, exist_ok=True)
    payload = snapshot.model_dump_json(indent=2)
    stamped = _INTEREST_DIR / f"snapshot-{ts_slug}.json"
    _atomic_write(stamped, payload)
    _atomic_write(_INTEREST_DIR / "latest.json", payload)
    return stamped


def load_latest() -> InterestSnapshot | None:
    """Load the most recent snapshot, or None if no run has happened yet."""
    path = _INTEREST_DIR / "latest.json"
    if not path.exists():
        return None
    return InterestSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
