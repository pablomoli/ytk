"""Interpret directives embedded in an ingest-hub thought (issue #14).

The thought stays verbatim in the note (`## My take`); this module only ADDS
links when the thought contains an actionable directive like "link this to
epicmap" or "add as a ref to the video about audiobooks".

Flow (mirrors the phase-5K triage pattern):
1. Cheap regex heuristic gates the LLM call — most thoughts are plain notes.
2. Candidate wikilink targets come from a semantic search over the vault;
   project slugs come from inbox/memories/. Both are handed to Haiku as the
   only legal values, with structured output enforced via tool-use.
3. Apply: append a `Related:` line of [[wikilinks]] to the ingested note and,
   when a project is named, a pointer line to that project's state atom.

Guardrails: max 3 links, outputs validated against the candidate lists,
user text is never rewritten or deleted.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from . import store, vault
from .sdk import structured

log = logging.getLogger(__name__)

MAX_LINKS = 3

# verbs that suggest the user is instructing, not just musing
_CUE = re.compile(
    r"\b(link|ref|reference|connect|relate|attach|file (this |it )?under"
    r"|pin (this |it )?to|add (this |it )?(as a ref|to))\b",
    re.IGNORECASE,
)


class Directive(BaseModel):
    is_directive: bool = False
    wikilinks: list[str] = Field(default_factory=list)
    project: str | None = None


def looks_like_directive(thought: str) -> bool:
    """Cheap gate: only thoughts with an imperative linking verb hit the LLM."""
    return bool(thought.strip()) and bool(_CUE.search(thought))


def list_project_slugs() -> list[str]:
    """Project slugs are the atom folders under inbox/memories/."""
    memories = vault._get_brain_path() / "inbox" / "memories"
    if not memories.exists():
        return []
    return sorted(p.name for p in memories.iterdir() if p.is_dir())


def _candidate_stems(thought: str, n: int = 8) -> list[str]:
    """Note stems the directive could plausibly point at, via semantic search."""
    brain = vault._get_brain_path()
    stems: list[str] = []
    for r in store.search_all(thought, n=n):
        if r.type == "memory" and r.source:
            stem = Path(r.source).stem
        else:
            # video results carry no path; the note filename is the title slug
            stem = vault._slug(r.title)
            if not list(brain.glob(f"sources/**/{stem}.md")):
                continue
        if stem and stem not in stems:
            stems.append(stem)
    return stems


_SYSTEM = """You interpret a short user note attached to a freshly ingested item in a personal knowledge vault.

Decide whether the note contains a DIRECTIVE: an instruction to link the ingested item to other notes or to a project. Musings, opinions, and reminders-to-self are NOT directives — set is_directive false and leave everything empty.

If it is a directive:
- wikilinks: pick at most {max_links} note stems from CANDIDATE NOTES that the user is referring to. Only use listed stems, verbatim. Omit if none match.
- project: pick the one slug from PROJECT SLUGS the user names (slugs are path-like; match on the project name inside them, e.g. "epicmap" -> the slug containing "epicmap"). null if no project is named.

Be conservative: a wrong link is worse than no link."""


def interpret(thought: str) -> Directive:
    """Run the Haiku pass. Raises on LLM failure; callers treat that as no-op."""
    candidates = _candidate_stems(thought)
    slugs = list_project_slugs()
    if not candidates and not slugs:
        return Directive()

    system = _SYSTEM.format(max_links=MAX_LINKS)
    prompt = (
        f"NOTE:\n{thought.strip()}\n\n"
        "CANDIDATE NOTES:\n" + "\n".join(f"- {s}" for s in candidates)
        + "\n\nPROJECT SLUGS:\n" + "\n".join(f"- {s}" for s in slugs)
    )
    d = structured(system, prompt, Directive)

    # trust nothing outside the candidate lists
    d.wikilinks = [w for w in d.wikilinks if w in candidates][:MAX_LINKS]
    if d.project not in slugs:
        d.project = None
    if not d.wikilinks and not d.project:
        d.is_directive = False
    return d


def apply(note_path: Path, directive: Directive, thought: str) -> list[str]:
    """Apply an interpreted directive. Returns human-readable lines for the
    ingest progress readout so bad links are caught immediately."""
    applied: list[str] = []
    if not directive.is_directive:
        return applied

    if directive.wikilinks:
        links = " ".join(f"[[{w}]]" for w in directive.wikilinks)
        text = note_path.read_text(encoding="utf-8")
        note_path.write_text(text.rstrip("\n") + f"\n\nRelated: {links}\n", encoding="utf-8")
        applied.append(f"linked {links}")

    if directive.project:
        snippet = " ".join(thought.split())
        if len(snippet) > 120:
            snippet = snippet[:120].rstrip() + "..."
        existing = vault.read_atom(directive.project, "state") or ""
        pointer = f"- [[{note_path.stem}]] (via ingest hub): {snippet}"
        vault.write_atom(directive.project, "state", (existing.rstrip("\n") + "\n" + pointer + "\n").lstrip("\n"))
        applied.append(f"pointed {directive.project}/state at [[{note_path.stem}]]")

    return applied


def process(note_path: Path, thought: str) -> list[str]:
    """Full pipeline for one annotated note: gate, interpret, apply.

    Never raises — directive interpretation must not fail an ingest.
    """
    try:
        if not looks_like_directive(thought):
            return []
        directive = interpret(thought)
        return apply(note_path, directive, thought)
    except Exception:
        log.warning("directive interpretation failed for %s", note_path, exc_info=True)
        return []
