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
    """A named cluster of notes that share a coherent topic or interest area."""

    id: str
    label: str
    summary: str
    weight: float
    note_ids: list[str]
    exemplar_titles: list[str]


class InterestSnapshot(BaseModel):
    """Complete output of one interest-model synthesis run.

    Persisted as JSON under ``~/.ytk/interest/``. The ``connections`` field is
    intentionally empty in Phase 0 and populated by later synthesis phases.
    """

    generated_at: str
    note_count: int
    themes: list[Theme]
    connections: list[Connection] = Field(default_factory=list)
    profile_markdown: str


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
