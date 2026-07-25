# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Deterministic domain assignment for the brain map's everything view.

A domain is the controlled top-level grouping axis. It used to be provenance:
the owning project for session/memory notes, parsed from the path, with the
interest-profile theme reaching only consumed content. That grouped the map by
directory first (#106) — half the canvas was one project slug and a quarter
was `other`.

The axis is now the user-authored bucket config at ~/.ytk/grove_buckets.yaml,
the same one the grove reads: one taste axis, two consumers. The two differ in
exactly one obligation — the grove renders only matched notes, while the map
must place every point, so notes matching no bucket get an explicit `unplaced`
class rather than vanishing or being handed a topic they do not belong to.

Pure functions; scripts/build_map.py wires them to real vectors and the theme
snapshot. The bucket matcher lives here rather than in scripts/grove_lab so
there is a single implementation and no import cycle with normalize_slug;
scripts/grove_lab/buckets.py re-exports it alongside its chroma glue.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

CONTENT_CATS = frozenset({"youtube", "instagram", "tiktok", "pinterest", "web", "screenshots"})
OTHER = "other"
# Matched no bucket. Rendered dim rather than dropped: the grove may omit what
# it cannot name, the map may not.
UNPLACED = "unplaced"
DEFAULT_CONFIG = Path.home() / ".ytk" / "grove_buckets.yaml"
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
    return [p if p and final_counts[p] >= min_size else OTHER for p in normalized]


@dataclass(frozen=True)
class Note:
    """A note reduced to the axes bucket rules can see."""

    cat: str
    project: str | None
    theme: str | None
    path: str


@dataclass
class Bucket:
    name: str
    palette: str | None = None
    projects: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    seed: str | None = None


@dataclass
class BucketConfig:
    buckets: list[Bucket]
    seed_floor: float
    version: int


def load_buckets(path: str | Path) -> BucketConfig:
    import yaml

    raw = yaml.safe_load(Path(path).read_text())
    buckets = [
        Bucket(
            name=b["name"],
            palette=b.get("palette"),
            projects=list(b.get("projects", [])),
            themes=list(b.get("themes", [])),
            paths=list(b.get("paths", [])),
            seed=b.get("seed"),
        )
        for b in raw.get("buckets", [])
    ]
    return BucketConfig(
        buckets=buckets,
        seed_floor=float(raw.get("seed_floor", 0.62)),
        version=int(raw.get("version", 1)),
    )


def _matches(note: Note, bucket: Bucket, declared: set[str]) -> bool:
    if note.project:
        slug = normalize_slug(note.project, declared)
        if slug in bucket.projects:
            return True
    if note.theme and note.theme in bucket.themes:
        return True
    return any(note.path.startswith(p) for p in bucket.paths)


def assign(notes: list[Note], cfg: BucketConfig) -> list[int]:
    """Bucket index per note, -1 when nothing matches. First bucket wins."""
    declared = {p for b in cfg.buckets for p in b.projects}
    out = []
    for note in notes:
        for i, bucket in enumerate(cfg.buckets):
            if _matches(note, bucket, declared):
                out.append(i)
                break
        else:
            out.append(-1)
    return out


def bucket_labels(notes: list[Note], cfg: BucketConfig) -> list[str]:
    """Per-point domain label on the bucket axis.

    No min_size collapse, unlike the provenance axis: a bucket the user
    authored is a bucket they meant, so a small one keeps its name instead of
    being folded into a residue class. Only genuinely unmatched notes go to
    `unplaced`.
    """
    return [cfg.buckets[i].name if i >= 0 else UNPLACED for i in assign(notes, cfg)]


def notes_from_metas(
    metas: list[dict],
    content_theme: dict[int, int],
    theme_labels: list[str],
    rel_path,
) -> list[Note]:
    """Reduce the map build's meta dicts to the axes bucket rules can see.

    rel_path is injected because vault-relative resolution needs the vault
    root, which is the caller's concern — these functions stay pure.
    """
    notes = []
    for i, m in enumerate(metas):
        ti = content_theme.get(i, -1) if m["cat"] in CONTENT_CATS else -1
        notes.append(
            Note(
                cat=m["cat"],
                project=project_from_path(m.get("path", "")),
                theme=theme_labels[ti] if ti >= 0 else None,
                path=rel_path(m.get("path", "")),
            )
        )
    return notes


def index_domains(labels: list[str]) -> tuple[list[int], list[dict]]:
    """Stable indexing: domains ordered by count descending, ties broken by
    first occurrence. Returns (per-point index, domain meta)."""
    counts = Counter(labels)
    ordered = [label for label, _ in counts.most_common()]
    index = {label: i for i, label in enumerate(ordered)}
    meta = [{"label": label, "n": counts[label]} for label in ordered]
    return [index[label] for label in labels], meta
