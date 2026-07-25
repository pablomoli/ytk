# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Recap: what came into the vault recently, and how it ties to recent work.

Shared core behind three surfaces: `ytk recap` (CLI), `POST /api/recap` (hub
button), and the `/whats-new` skill. The split is deliberate:

- `gather_recent()` collects the newest ingested notes plus recent-work signals
  (ideas backlog, journal, interest themes) and grounds each ingest against the
  memory store so connections rest on real neighbours, not guesses.
- `render_context()` dumps that as markdown with **zero API calls** — the skill
  consumes this and lets the interactive session narrate.
- `synthesize()` makes one Claude call to narrate the throughline and ties.

Everything the store touches is best-effort: a cold or failing embedder degrades
the grounding, it never aborts the recap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from ytk import vault

_SUMMARY_CAP = 500  # per-ingest, keeps 12 notes under the synthesis input budget
_IDEAS_CAP = 2000
_JOURNAL_CAP = 1500


@dataclass
class RelatedNote:
    title: str
    path: str
    distance: float


@dataclass
class RecentIngest:
    title: str
    source_type: str
    url: str
    date: str
    tags: list[str]
    summary: str
    path: str  # vault-relative
    related: list[RelatedNote] = field(default_factory=list)


@dataclass
class RecapContext:
    ingests: list[RecentIngest]
    ideas: str
    journal: str
    themes: list[str]


class RecapNarrative(BaseModel):
    narrative: str


_FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def _parse_frontmatter(fm: str) -> dict:
    """Minimal YAML-subset parser for the flat frontmatter ytk writes.

    Handles `key: value` scalars and block lists (`key:` then `  - item`). Good
    enough for the fields a recap needs; a full YAML dep would be overkill for
    frontmatter this regular.
    """
    data: dict = {}
    key: str | None = None
    for line in fm.splitlines():
        if not line.strip():
            continue
        item = re.match(r"\s+-\s+(.*)", line)
        if item and key:
            data.setdefault(key, [])
            if isinstance(data[key], list):
                data[key].append(item.group(1).strip())
            continue
        m = re.match(r"(\w[\w-]*):\s*(.*)", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            data[key] = val or []
    return data


def _extract_summary(body: str) -> str:
    """Pull the ## Summary section, falling back to ## Thesis, then first prose."""
    for heading in ("Summary", "Thesis", "Caption"):
        m = re.search(rf"^##\s+{heading}\s*\n(.*?)(?=\n##\s|\Z)", body, re.DOTALL | re.MULTILINE)
        if m and m.group(1).strip():
            return m.group(1).strip()
    # No known section: take the first non-embed paragraph.
    for para in re.split(r"\n\s*\n", body):
        text = re.sub(r"!\[\[.*?\]\]", "", para).strip()
        if text and not text.startswith("#"):
            return text
    return ""


def _parse_ingest(path: Path, brain: Path) -> RecentIngest:
    raw = path.read_text(encoding="utf-8", errors="replace")
    fm_match = _FM_RE.match(raw)
    fm = _parse_frontmatter(fm_match.group(1)) if fm_match else {}
    body = raw[fm_match.end() :] if fm_match else raw
    raw_tags = fm.get("tags")
    tags = raw_tags if isinstance(raw_tags, list) else []
    rel = str(path.relative_to(brain))
    return RecentIngest(
        title=str(fm.get("title") or path.stem),
        source_type=str(fm.get("type") or path.parent.name),
        url=str(fm.get("url") or ""),
        date=str(fm.get("date") or ""),
        tags=[str(t) for t in tags],
        summary=_extract_summary(body)[:_SUMMARY_CAP],
        path=rel,
    )


def _newest_source_notes(brain: Path, n: int) -> list[Path]:
    """Newest N notes under sources/ by mtime — when they entered the vault,
    which is what 'recently ingested' means (the `date:` field is the media's
    own date and can be years old)."""
    sources = brain / "sources"
    if not sources.exists():
        return []
    notes = [p for p in sources.glob("**/*.md") if p.is_file()]
    notes.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return notes[:n]


def _ground(ingest: RecentIngest, k: int = 2) -> list[RelatedNote]:
    """Nearest existing notes to this ingest, itself excluded. Best-effort: any
    store failure (cold embedder, empty collection) yields no grounding."""
    try:
        from ytk import store

        query = ingest.summary or ingest.title
        if not query:
            return []
        results = store.search_all(query, n=k + 2)
    except Exception:
        return []
    out: list[RelatedNote] = []
    for r in results:
        # Drop the ingest itself: its own note path or url resurfacing as a hit.
        if ingest.path and r.source and ingest.path in r.source:
            continue
        if ingest.url and r.source == ingest.url:
            continue
        out.append(RelatedNote(title=r.title, path=r.source, distance=r.distance))
        if len(out) >= k:
            break
    return out


def _read_capped(brain: Path, rel: str, cap: int) -> str:
    path = brain / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()[:cap]


def _journal_recent(brain: Path) -> str:
    """The 'Recent entries' block from the journal hub — one line per recent day,
    the densest available read on what's currently on the user's mind."""
    hub = _read_capped(brain, "me/journal.md", 6000)
    if not hub:
        return ""
    m = re.search(r"##\s+Recent entries\s*\n(.*?)(?=\n##\s|\Z)", hub, re.DOTALL)
    block = (m.group(1) if m else hub).strip()
    return block[:_JOURNAL_CAP]


def _themes(top: int = 8) -> list[str]:
    try:
        from ytk import interest

        snap = interest.load_latest()
    except Exception:
        return []
    if not snap:
        return []
    return [t.label for t in snap.themes[:top]]


def gather_recent(n: int = 12, ground: bool = True) -> RecapContext:
    """Collect the newest N ingests + recent-work signals for a recap."""
    brain = vault._get_brain_path()
    ingests = [_parse_ingest(p, brain) for p in _newest_source_notes(brain, n)]
    if ground:
        for ing in ingests:
            ing.related = _ground(ing)
    return RecapContext(
        ingests=ingests,
        ideas=_read_capped(brain, "inbox/ideas.md", _IDEAS_CAP),
        journal=_journal_recent(brain),
        themes=_themes(),
    )


def render_context(ctx: RecapContext) -> str:
    """Deterministic markdown dump of the gathered material. No API call — this
    is what the /whats-new skill reads before narrating in-session."""
    lines: list[str] = ["# Recap material", ""]
    lines.append(f"## Recently ingested ({len(ctx.ingests)})")
    for i, ing in enumerate(ctx.ingests, 1):
        tags = f" · tags: {', '.join(ing.tags)}" if ing.tags else ""
        lines.append(f"\n### {i}. {ing.title}")
        lines.append(f"- source: {ing.source_type}{tags}")
        if ing.date:
            lines.append(f"- date: {ing.date}")
        lines.append(f"- note: [[{Path(ing.path).stem}]]")
        if ing.url:
            lines.append(f"- url: {ing.url}")
        if ing.summary:
            lines.append(f"- summary: {ing.summary}")
        if ing.related:
            near = "; ".join(f"[[{Path(r.path).stem}]] ({r.distance:.2f})" for r in ing.related)
            lines.append(f"- sits near: {near}")
    if ctx.themes:
        lines.append("\n## Your interest themes")
        lines.append(", ".join(ctx.themes))
    if ctx.ideas:
        lines.append("\n## Your ideas backlog (inbox/ideas.md)")
        lines.append(ctx.ideas)
    if ctx.journal:
        lines.append("\n## Recent journal entries")
        lines.append(ctx.journal)
    return "\n".join(lines)


_SYSTEM = (
    "You are the user's knowledge companion inside ytk, their personal YouTube/"
    "Instagram/reading knowledge vault. ytk is a complement to consuming, not a "
    "replacement: the user watches and reads a lot and wants help seeing what it "
    "adds up to and how it feeds their own work.\n\n"
    "You are given a batch of recently ingested notes plus signals about what the "
    "user is currently working on and thinking about (their ideas backlog, "
    "interest themes, and recent journal lines). For each ingest you are also told "
    "which existing vault notes it 'sits near' semantically.\n\n"
    "Write a tight, specific recap in markdown. Requirements:\n"
    "- Open with one or two sentences naming the throughline across what came in.\n"
    "- Then draw concrete connections to the user's own work/ideas/themes. Ground "
    "every claimed connection in the provided material — cite the related note "
    "with a [[wikilink]] when you say two things connect. Never invent a note.\n"
    "- Group related ingests rather than marching through all twelve one by one.\n"
    "- Name the actual tools, techniques, and ideas; skip generic praise.\n"
    "- End with one short 'worth acting on' line only if something genuinely "
    "connects to an idea in the backlog.\n"
    "Keep it under ~450 words. Return only the markdown narrative."
)


def synthesize(ctx: RecapContext, model: str = "claude-haiku-4-5") -> str:
    """One Claude call turning gathered material into a grounded narrative."""
    from ytk import sdk

    if not ctx.ingests:
        return "_Nothing has been ingested yet — the recap has nothing to work with._"
    result = sdk.structured(
        _SYSTEM,
        render_context(ctx),
        RecapNarrative,
        model=model,
        max_input_chars=40_000,
        max_tokens=2000,
    )
    return result.narrative.strip()
