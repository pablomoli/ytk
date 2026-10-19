"""Factual links, linking layer 1: creator and concept hubs.

A hub is a note per creator with 2+ source notes and per Key Concept name in
2+ source notes. Each source note links to its hubs from frontmatter
properties (`creator`, `concepts`), so the body, and therefore every
embedding, stays as it was. Deterministic; no model calls.

Links are generated from the owner's reviewed list (`hub_verdicts` in the
ledger): only approved names link, a struck name loses every link on the next
apply, and a name nobody has judged writes nothing.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from . import ledger

CREATOR = "creator"
CONCEPT = "concept"
KINDS = (CREATOR, CONCEPT)
THRESHOLD = 2
# Measured order of precedence: `author` is how web notes name their creator.
CREATOR_KEYS = ("uploader", "channel", "author")
HUBS_DIR = "links"
SUBDIR = {CREATOR: "creators", CONCEPT: "concepts"}
PROPERTY = {CREATOR: "creator", CONCEPT: "concepts"}
GENERATED_BY = "ytk-hubs"
VERDICTS = ("approve", "strike")
EXAMPLES = 3

_FM = re.compile(r"\A---\n(.*?)^---[ \t]*\n?", re.DOTALL | re.MULTILINE)
_KEY_CONCEPTS = re.compile(r"^## Key Concepts[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
_LINK_VALUE = re.compile(r'^"\[\[[^\]\n]+\]\]"$')
_UNSAFE = re.compile(r'[\[\]#^|\\/:*?"<>\n\r\t]+')
_SKIP_DIRS = {".obsidian", ".trash", ".git"}

_APPLY_LOCK = threading.Lock()


def normalize_concept(name: str) -> str:
    """Lowercase, punctuation and whitespace collapsed to single spaces.

    ASCII-only first, so "Measure μ" and "measure" meet; a name with no ASCII
    letters at all falls back to its Unicode word characters.
    """
    folded = " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())
    if folded:
        return folded
    return " ".join(re.sub(r"[\W_]+", " ", name.casefold()).split())


def normalize_creator(name: str) -> str:
    return " ".join(name.casefold().split())


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    m = _FM.match(text)
    if not m:
        return None
    return m.group(1), text[m.end() :]


def _scalar(fm: str, key: str) -> str:
    m = re.search(rf"^{key}:[ \t]*(.*)$", fm, re.MULTILINE)
    if not m:
        return ""
    return m.group(1).strip().strip("\"'").strip()


def concept_names(body: str) -> list[str]:
    """Raw names from the Key Concepts section: the text before the first ': '."""
    m = _KEY_CONCEPTS.search(body)
    if not m:
        return []
    names: list[str] = []
    for line in m.group(1).splitlines():
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        name = item.split(": ", 1)[0] if ": " in item else item
        name = name.strip().strip("*").strip()
        if name:
            names.append(name)
    return names


@dataclass
class NoteFacts:
    path: Path
    title: str
    has_frontmatter: bool
    creator: str = ""
    concepts: list[str] = field(default_factory=list[str])


def read_note(path: Path) -> NoteFacts:
    text = path.read_text(encoding="utf-8", errors="replace")
    split = _split_frontmatter(text)
    fm, body = split or ("", text)
    creator = next((v for k in CREATOR_KEYS if (v := _scalar(fm, k))), "")
    return NoteFacts(
        path=path,
        title=_scalar(fm, "title") or path.stem,
        has_frontmatter=split is not None,
        creator=creator,
        concepts=concept_names(body),
    )


def scan_sources(brain: Path) -> list[NoteFacts]:
    sources = brain / "sources"
    if not sources.is_dir():
        return []
    return [read_note(p) for p in sorted(sources.rglob("*.md")) if p.is_file()]


# --- review state ---------------------------------------------------------


def record_verdicts(
    conn: sqlite3.Connection,
    verdicts: list[tuple[str, str, str]],
    *,
    surface: str,
    judged_by: str = "owner",
) -> int:
    """Append (kind, key, verdict) rows that change the current verdict.

    History is kept: the current verdict is the latest row per (kind, key).
    """
    current = current_verdicts(conn)
    at = ledger.now()
    rows: list[tuple[str, str, str, str, str, str]] = []
    for kind, key, verdict in verdicts:
        if kind not in KINDS or verdict not in VERDICTS or not key:
            raise ValueError(f"bad verdict {kind!r} {key!r} {verdict!r}")
        if current.get((kind, key), (None,))[0] != verdict:
            rows.append((kind, key, verdict, at, judged_by, surface))
    conn.executemany(
        "INSERT INTO hub_verdicts (kind, key, verdict, at, judged_by, surface)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def current_verdicts(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, str]]:
    """(kind, key) -> (verdict, at) for every judged name."""
    rows = conn.execute(
        "SELECT kind, key, verdict, at FROM hub_verdicts h WHERE id ="
        " (SELECT MAX(id) FROM hub_verdicts WHERE kind = h.kind AND key = h.key)"
    ).fetchall()
    return {(r["kind"], r["key"]): (r["verdict"], r["at"]) for r in rows}


# --- candidates -----------------------------------------------------------


@dataclass
class Candidate:
    kind: str
    key: str
    name: str
    count: int
    notes: list[NoteFacts]
    examples: list[str]
    target: str = ""
    target_path: str = ""
    hand_made: bool = False
    collision: str = ""
    verdict: str = "pending"
    judged_at: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "key": self.key,
            "name": self.name,
            "count": self.count,
            "examples": self.examples,
            "target": self.target,
            "target_path": self.target_path,
            "hand_made": self.hand_made,
            "collision": self.collision,
            "verdict": self.verdict,
            "judged_at": self.judged_at,
        }


def safe_basename(name: str) -> str:
    """A file and wikilink-safe basename: no characters Obsidian links break on."""
    out = " ".join(_UNSAFE.sub(" ", name).split()).lstrip(".").strip()
    return out[:120].rstrip()


def _is_generated(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return False
    split = _split_frontmatter(head + "\n")
    return bool(split) and _scalar(split[0], "generated_by") == GENERATED_BY


def _basename_index(vault_root: Path, hubs_root: Path) -> dict[str, list[Path]]:
    """casefolded basename -> vault .md files, minus generated hubs (ours to rewrite)."""
    index: dict[str, list[Path]] = defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(vault_root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for fn in sorted(filenames):
            if not fn.endswith(".md"):
                continue
            path = Path(dirpath) / fn
            if path.is_relative_to(hubs_root) and _is_generated(path):
                continue
            index[path.stem.casefold()].append(path)
    return index


def build_candidates(
    brain: Path,
    facts: list[NoteFacts],
    verdicts: dict[tuple[str, str], tuple[str, str]],
) -> list[Candidate]:
    """Every name in 2+ notes, sorted by note count descending, targets resolved."""
    notes: dict[tuple[str, str], list[NoteFacts]] = defaultdict(list)
    forms: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for f in facts:
        if f.creator:
            k = (CREATOR, normalize_creator(f.creator))
            notes[k].append(f)
            forms[k][f.creator] += 1
        seen: set[str] = set()
        for raw in f.concepts:
            key = normalize_concept(raw)
            if not key:
                continue
            forms[(CONCEPT, key)][raw] += 1
            if key not in seen:
                seen.add(key)
                notes[(CONCEPT, key)].append(f)

    out: list[Candidate] = []
    for (kind, key), members in notes.items():
        if len(members) < THRESHOLD:
            continue
        # Most frequent surface form names the hub; ties break alphabetically.
        name = min(forms[(kind, key)].items(), key=lambda kv: (-kv[1], kv[0]))[0]
        verdict, at = verdicts.get((kind, key), ("pending", ""))
        out.append(
            Candidate(
                kind=kind,
                key=key,
                name=name,
                count=len(members),
                notes=members,
                examples=[m.title for m in members[:EXAMPLES]],
                verdict=verdict,
                judged_at=at,
            )
        )
    out.sort(key=lambda c: (-c.count, c.kind, c.key))
    _resolve_targets(brain, out)
    return out


def _resolve_targets(brain: Path, candidates: list[Candidate]) -> None:
    """Point each candidate at a hand-made note of the same name, or at a
    generated hub whose basename is unique across the whole vault."""
    vault_root = brain.parent
    hubs_root = brain / HUBS_DIR
    index = _basename_index(vault_root, hubs_root)
    sources = brain / "sources"
    reserved: set[str] = set()

    def rel(p: Path) -> str:
        return p.relative_to(vault_root).as_posix()

    # Concepts claim plain names first so a creator sharing a name is the one suffixed.
    for cand in sorted(candidates, key=lambda c: (c.kind != CONCEPT, -c.count, c.key)):
        base = safe_basename(cand.name) or safe_basename(cand.key)
        clashes = index.get(base.casefold(), [])
        hand = [p for p in clashes if p.is_relative_to(brain) and not p.is_relative_to(sources)]
        if hand:
            cand.hand_made = True
            cand.target = hand[0].stem
            cand.target_path = rel(hand[0])
            reserved.add(base.casefold())
            cand.collision = ", ".join(rel(p) for p in clashes if p != hand[0])
            continue
        target = base
        if clashes or target.casefold() in reserved:
            cand.collision = ", ".join(rel(p) for p in clashes) or "another hub"
            target = f"{base} ({cand.kind})"
            n = 2
            while index.get(target.casefold()) or target.casefold() in reserved:
                target = f"{base} ({cand.kind} {n})"
                n += 1
        reserved.add(target.casefold())
        cand.target = target
        cand.target_path = rel(hubs_root / SUBDIR[cand.kind] / f"{target}.md")


def candidates(conn: sqlite3.Connection, brain: Path | None = None) -> list[Candidate]:
    from . import vault

    brain = brain or vault.get_brain_path()
    return build_candidates(brain, scan_sources(brain), current_verdicts(conn))


# --- writing --------------------------------------------------------------


def _owned_span(fm: str, key: str) -> tuple[int, int] | Literal[False] | None:
    """Span of an owned property in frontmatter text, None when absent, False
    when the key exists but holds something other than quoted wikilinks."""
    m = re.search(rf"^{key}:[ \t]*(.*)\n((?:[ \t]+-.*\n)*)", fm, re.MULTILINE)
    if not m:
        return None
    inline = m.group(1).strip()
    items = [ln.strip()[1:].strip() for ln in m.group(2).splitlines()]
    if inline.startswith("[") and inline.endswith("]") and not items:
        items = [v.strip() for v in inline[1:-1].split(",") if v.strip()]
    elif inline:
        items = [inline, *items]
    if not items or not all(_LINK_VALUE.match(v) for v in items):
        return False
    return m.start(), m.end()


def set_links(text: str, creator: str | None, concepts: list[str]) -> tuple[str, list[str]]:
    """Rewrite the owned properties; returns (new text, keys left alone).

    Owned means the value is quoted wikilinks only. A key holding anything
    else was written by a person and is never touched or overwritten.
    """
    m = _FM.match(text)
    if m is None:
        return text, []
    fm = original = m.group(1)
    wanted = {PROPERTY[CREATOR]: [creator] if creator else [], PROPERTY[CONCEPT]: concepts}
    foreign: list[str] = []
    for key in wanted:
        span = _owned_span(fm, key)
        if span is False:
            if wanted[key]:
                foreign.append(key)
        elif isinstance(span, tuple):
            fm = fm[: span[0]] + fm[span[1] :]
    if creator and _owned_span(fm, PROPERTY[CREATOR]) is None:
        fm += f'{PROPERTY[CREATOR]}: "[[{creator}]]"\n'
    if concepts and _owned_span(fm, PROPERTY[CONCEPT]) is None:
        fm += f"{PROPERTY[CONCEPT]}:\n" + "".join(f'  - "[[{c}]]"\n' for c in concepts)
    if fm == original:
        return text, foreign
    return text[: m.start(1)] + fm + text[m.end(1) :], foreign


def _write_keep_mtime(path: Path, text: str) -> None:
    # The digest ranks notes by mtime; a link is not new content.
    st = path.stat()
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))


def hub_text(cand: Candidate, brain: Path) -> str:
    vault_root = brain.parent
    label = "Creator" if cand.kind == CREATOR else "Concept"
    rows: list[str] = []
    for f in sorted(cand.notes, key=lambda f: f.path.stem.casefold()):
        rel = f.path.relative_to(vault_root).with_suffix("").as_posix()
        title = safe_basename(f.title) or f.path.stem
        rows.append(f"- [[{rel}|{title}]]")
    return (
        "---\n"
        f"generated_by: {GENERATED_BY}\n"
        f"hub_kind: {cand.kind}\n"
        f'hub_key: "{cand.key}"\n'
        "---\n\n"
        f"# {cand.name}\n\n"
        f"{label} hub: {cand.count} source notes. Generated from the reviewed hub list;"
        " edits here are overwritten.\n\n" + "\n".join(rows) + "\n"
    )


@dataclass
class ApplyReport:
    notes_scanned: int = 0
    approved: int = 0
    struck: int = 0
    pending: int = 0
    notes_linked: int = 0
    links: int = 0
    notes_changed: int = 0
    hubs_written: int = 0
    hubs_removed: int = 0
    hand_made_targets: int = 0
    collisions: int = 0
    no_frontmatter: list[str] = field(default_factory=list[str])
    foreign_keys: list[str] = field(default_factory=list[str])
    dry_run: bool = False

    def as_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


def apply(
    conn: sqlite3.Connection, brain: Path | None = None, *, dry_run: bool = False
) -> ApplyReport:
    """Make the vault match the reviewed list. Idempotent: a second run writes nothing."""
    from . import vault

    brain = brain or vault.get_brain_path()
    with _APPLY_LOCK:
        facts = scan_sources(brain)
        cands = build_candidates(brain, facts, current_verdicts(conn))
        return _apply(brain, facts, cands, dry_run)


def _apply(
    brain: Path, facts: list[NoteFacts], cands: list[Candidate], dry_run: bool
) -> ApplyReport:
    vault_root = brain.parent
    report = ApplyReport(notes_scanned=len(facts), dry_run=dry_run)
    active: dict[tuple[str, str], Candidate] = {}
    for c in cands:
        report.approved += c.verdict == "approve"
        report.struck += c.verdict == "strike"
        report.pending += c.verdict == "pending"
        if c.verdict == "approve":
            active[(c.kind, c.key)] = c
            report.hand_made_targets += c.hand_made
            report.collisions += bool(c.collision)

    for f in facts:
        hit = active.get((CREATOR, normalize_creator(f.creator))) if f.creator else None
        creator = hit.target if hit else None
        concepts: list[str] = []
        for raw in f.concepts:
            c = active.get((CONCEPT, normalize_concept(raw)))
            if c and c.target not in concepts:
                concepts.append(c.target)
        if creator or concepts:
            report.notes_linked += 1
            report.links += bool(creator) + len(concepts)
        rel = f.path.relative_to(vault_root).as_posix()
        if not f.has_frontmatter:
            if creator or concepts:
                report.no_frontmatter.append(rel)
            continue
        text = f.path.read_text(encoding="utf-8", errors="replace")
        new, foreign = set_links(text, creator, concepts)
        report.foreign_keys.extend(f"{rel}: {k}" for k in foreign)
        if new != text:
            report.notes_changed += 1
            if not dry_run:
                _write_keep_mtime(f.path, new)

    hubs_root = brain / HUBS_DIR
    keep: set[Path] = set()
    for c in active.values():
        if c.hand_made:
            continue
        path = vault_root / c.target_path
        keep.add(path)
        text = hub_text(c, brain)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        report.hubs_written += 1
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if hubs_root.is_dir():
        for path in sorted(hubs_root.rglob("*.md")):
            if path not in keep and _is_generated(path):
                report.hubs_removed += 1
                if not dry_run:
                    path.unlink()
    return report


def link_landed(conn: sqlite3.Connection) -> ApplyReport | None:
    """Run after a note lands. Nothing to do until the owner approves a name;
    a name the landing pushes past the threshold shows up as pending."""
    row = conn.execute("SELECT 1 FROM hub_verdicts WHERE verdict = 'approve' LIMIT 1").fetchone()
    if row is None:
        return None
    return apply(conn)


def summary(cands: list[Candidate]) -> dict[str, dict[str, int]]:
    by = Counter((c.kind, c.verdict) for c in cands)
    return {
        kind: {
            "names": sum(n for (k, _), n in by.items() if k == kind),
            **{v: by[(kind, v)] for v in ("pending", *VERDICTS)},
            "notes": len({f.path for c in cands if c.kind == kind for f in c.notes}),
        }
        for kind in KINDS
    }
