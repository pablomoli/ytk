"""The connect verb (#197 P6): an accepted note gets proposed links, each
with a one-clause argument tied to the thesis. Writes nothing to the vault
— the owner approves at the digest, and only the loop applies survivors
(snapshot first). AI links are worthless unless the owner made them; bulk
generated links degrade search (spec, What the research says).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from . import asks, ledger

# Candidate band. Floor: p25 of the top-1 non-self cosine on the query path
# that ships (thesis + one query per key concept, both collections, union),
# 30 random content notes, 2026-09-06: min 0.413, p25 0.507, median 0.579,
# p75 0.632, max 0.791. Re-measure with scripts/measure_connect_floor.py
# whenever the query path or the encoder changes; the old blob path read
# median 0.518 on the same notes, and 0.55 there muted two landings in
# three. A relative rule (top 5 within 0.08 of the item's own best) was
# rejected: it admitted five candidates for 22 of 30 notes and can never
# say "no relatives", which is the one free outcome worth keeping.
# Ceiling: NEAR_DUP_BASELINE, the formal dup boundary; on this path it
# only ever catches the item's own note.
CANDIDATE_FLOOR = 0.50
MAX_CANDIDATES = 5
# Over-fetch before the band cut; a video can match on parts that collapse.
_FETCH_N = 12

# Sonnet, the enricher tier: connect proposes, it never judges. The wall
# against the grader is the same as the enricher's — no rubric in any
# prompt here (pinned in tests).
from .enricher import ENRICHER_MODEL as CONNECT_MODEL  # noqa: E402


class Candidate(BaseModel):
    target: str  # vault note basename; Obsidian resolves [[target]] vault-wide
    target_title: str
    thesis: str
    cosine: float
    via: str = "thesis"  # the query label that earned the cosine: thesis or a concept name
    path: str | None = None  # the resolved note, for readers that need more than its name


class ProposedLink(BaseModel):
    target: str
    target_title: str
    argument: str


# Indexed for search, never a link target: the identity layer, listings,
# digests, session records and the claude-mem summaries all describe the
# vault instead of belonging to it. A link is a note the owner would open
# next; the atom that carries the same fact still qualifies.
_UNLINKABLE_PREFIXES = ("wiki/", "me/", "hub/", "inbox/memories/claude-mem/")
_UNLINKABLE_PATTERNS = (
    re.compile(r"^inbox/(review(-[^/]+)?|dashboard|(inbox/)?ideas)\.md$"),
    re.compile(r"^projects/.+/session-[^/]+-brief\.md$"),
    re.compile(r"^(.+/)?_?templates/"),
)


def _linkable(note: Path, brain: Path) -> bool:
    try:
        rel = note.relative_to(brain).as_posix()
    except ValueError:
        return False
    if rel.startswith(_UNLINKABLE_PREFIXES):
        return False
    return not any(p.match(rel) for p in _UNLINKABLE_PATTERNS)


def _note_identity(note: Path, fallback_title: str, fallback_thesis: str) -> tuple[str, str]:
    """title from frontmatter and the first paragraph under Thesis (or the
    legacy Summary) — the two lines the argue prompt names a candidate by.
    Memory hits carry neither; the note on disk is the one source."""
    try:
        head = note.read_text(encoding="utf-8")[:6000]
    except OSError:
        return fallback_title, fallback_thesis
    title = fallback_title
    for pat in (r"^title:\s*(.+)$", r"^# (.+)$"):
        m = re.search(pat, head, re.MULTILINE)
        if m and m.group(1).strip():
            title = m.group(1).strip().strip("\"'")
            break
    thesis = fallback_thesis
    for heading in ("## Thesis", "## Summary"):
        m = re.search(
            rf"^{re.escape(heading)}\s*\n+(.+?)(?:\n\s*\n|\n## |\Z)", head, re.MULTILINE | re.DOTALL
        )
        if m and m.group(1).strip():
            thesis = " ".join(m.group(1).split())
            break
    return title, thesis


def _note_url(note: Path) -> str | None:
    try:
        head = note.read_text(encoding="utf-8")[:2000]
    except OSError:
        return None
    m = re.search(r"^url:\s*(\S+)\s*$", head, re.MULTILINE)
    return m.group(1) if m else None


def concept_label(concept: str) -> str:
    """The name before the enricher's colon ("Triposplat: the open-source
    project ..." -> "Triposplat"); the whole line, clipped, when there is
    none."""
    head = concept.split(":", 1)[0].strip() if ":" in concept[:80] else concept.strip()
    return head[:60] or concept[:60]


TAKE_LABEL = "the owner's take"
NOTE_LABEL = "the whole note"


def build_queries(
    thesis: str, key_concepts: list[str] | None, take: str | None = None
) -> list[tuple[str, str]]:
    """(label, text) pairs: the owner's take first when there is one, the
    thesis, then one query per key concept. The summary is left out on
    purpose — folded into one blob its generic half wins the match (#210,
    measured on the splats reel)."""
    out: list[tuple[str, str]] = []
    if take and take.strip():
        out.append((TAKE_LABEL, take.strip()))
    out.append(("thesis", thesis))
    for concept in key_concepts or []:
        if concept.strip():
            out.append((concept_label(concept), concept))
    return out


# Linkable content lives here; the take's literal lookups scan nothing else.
_CONTENT_DIRS = ("sources", "inbox/memories", "study", "decisions", "debugging", "tools", "notes")
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_HANDLE = re.compile(r"(?<![\w.])@([A-Za-z0-9_.]{2,30})")
_ISSUE = re.compile(r"(?<![\w&])#(\d{1,5})(?!\d)")


def _content_notes(brain: Path) -> list[Path]:
    out: list[Path] = []
    for d in _CONTENT_DIRS:
        root = brain / d
        if root.is_dir():
            out.extend(root.rglob("*.md"))
    return out


def _uploader_of(note: Path) -> str | None:
    try:
        head = note.read_text(encoding="utf-8")[:2000]
    except OSError:
        return None
    m = re.search(r"^uploader:\s*(.+)$", head, re.MULTILINE)
    return m.group(1).strip().strip("\"'") if m else None


class TakeReading(BaseModel):
    """What the owner's take names. `named` are notes the take points at
    outright ([[wikilinks]]), candidates at cosine 1.0 with no search.
    `promote` maps notes the take names as a set (every note filed under an
    @handle, by a creator, or citing a #NNN issue) to what named them; the
    store decides which members are about this item, and those come back
    at cosine 1.0 too. The take says who, the store says which."""

    named: list[Candidate] = []
    promote: dict[Path, str] = {}


def read_take(take: str | None, *, exclude_path: Path | None = None) -> TakeReading:
    """Read the take before the store: a [[wikilink]] is a candidate as is;
    an @handle, a creator's name (uploader frontmatter, whole words) or a
    #NNN issue names the set of notes to promote when the search reaches
    them."""
    if not take or not take.strip():
        return TakeReading()
    try:
        from . import vault

        brain = vault.get_brain_path()
    except Exception:
        return TakeReading()
    own = exclude_path.resolve() if exclude_path else None
    named: dict[Path, Candidate] = {}
    promote: dict[Path, str] = {}

    def usable(note: Path) -> Path | None:
        if not note.is_file() or not _linkable(note, brain):
            return None
        resolved = note.resolve()
        return None if resolved == own else resolved

    for name in _WIKILINK.findall(take):
        target = Path(name.strip())
        direct = brain / target.with_suffix(".md")
        matches = [direct] if direct.is_file() else list(brain.rglob(f"{target.name}.md"))
        for note in matches:
            resolved = usable(note)
            if resolved is None or resolved in named:
                continue
            title, thesis = _note_identity(note, note.stem, "")
            named[resolved] = Candidate(
                target=note.stem,
                target_title=title,
                thesis=thesis,
                cosine=1.0,
                via=TAKE_LABEL,
                path=str(resolved),
            )

    handles = [h.lower().rstrip(".") for h in _HANDLE.findall(take)]
    issues = _ISSUE.findall(take)
    issue_pattern = re.compile(r"#(?:" + "|".join(issues) + r")(?!\d)") if issues else None
    for note in _content_notes(brain):
        why: str | None = None
        stem = note.stem.lower()
        handle = next((h for h in handles if stem == h or stem.startswith(h + "-")), None)
        if handle:
            why = f"@{handle}"
        elif note.parent.name == "youtube":
            uploader = _uploader_of(note)
            # Whole words, four characters up: "Ally" matched "really" as a substring.
            if (
                uploader
                and len(uploader) >= 4
                and re.search(rf"(?<!\w){re.escape(uploader.lower())}(?!\w)", take.lower())
            ):
                why = uploader
        if why is None and issue_pattern is not None:
            try:
                m = issue_pattern.search(note.read_text(encoding="utf-8"))
            except OSError:
                m = None
            if m:
                why = m.group(0)
        if why is None:
            continue
        resolved = usable(note)
        if resolved is not None and resolved not in named:
            promote.setdefault(resolved, why)
    return TakeReading(named=list(named.values()), promote=promote)


def merge_candidates(named: list[Candidate], found: list[Candidate]) -> list[Candidate]:
    """The take's candidates first and never dropped; the store's fill the
    cap behind them without repeating a target."""
    seen = {c.target for c in named}
    out = list(named)
    for c in found:
        if c.target in seen:
            continue
        if len(out) >= MAX_CANDIDATES:
            break
        seen.add(c.target)
        out.append(c)
    return out


def own_vector(note_path: Path | None, media_id: str | None) -> list[float] | None:
    """The landed note's stored position, or None (store down, not indexed)."""
    try:
        from . import store

        return store.note_vector(
            source_path=str(note_path) if note_path else None, video_id=media_id
        )
    except Exception:
        return None


def find_candidates(
    queries: list[tuple[str, str]],
    *,
    exclude_media_id: str | None,
    exclude_url: str | None = None,
    exclude_path: Path | None = None,
    promote: dict[Path, str] | None = None,
    report: dict[str, Any] | None = None,
    vector: list[float] | None = None,
    exclude_targets: set[str] | None = None,
) -> list[Candidate]:
    """Neighbors across both collections for every (label, query) pair,
    unioned by note with the best cosine kept and the label that earned it,
    cut to the band [CANDIDATE_FLOOR, NEAR_DUP_BASELINE), resolved to vault
    notes, capped. Video hits resolve by url, memory hits by their indexed
    source_path; the item's own note is excluded by media id, url or path.
    A hit on a note in `promote` (named by the owner's take) skips the floor
    and comes back first at cosine 1.0. The one transport seam kernel 1
    replaces in P7; None-tolerant when the store is down (no candidates,
    never a failure). `report`, when given, receives the best hit under the
    floor as (cosine, label), so an empty result says how far from the band
    the nearest relative sat instead of hiding a true absence (#214).
    `vector`, the note's own stored position, adds its doc-to-doc
    neighbours as one more source under NOTE_LABEL, same band and cap.
    `exclude_targets`, note basenames already linked, drop before the cap."""
    from .grader import NEAR_DUP_BASELINE

    promote_paths = {p.resolve() for p in (promote or {})}
    promote_urls = {u for p in promote_paths if (u := _note_url(p))}

    def promotable(r: Any) -> bool:
        if not promote_paths:
            return False
        if r.type == "video":
            return r.source in promote_urls
        return bool(r.source) and Path(r.source).resolve() in promote_paths

    try:
        from . import store, vault

        brain = vault.get_brain_path()
        # (type, doc id) -> best (cosine, label, hit, promoted); the band
        # cut runs on raw hits so only survivors pay for a note lookup.
        best: dict[tuple[str, str], tuple[float, str, Any, bool]] = {}
        sources: list[tuple[str, list[Any]]] = [
            (label, store.search_all(text, n=_FETCH_N, rerank=False, actor="connect"))
            for label, text in queries
        ]
        if vector is not None:
            sources.append((NOTE_LABEL, store.search_vector(vector, n=_FETCH_N)))
        for label, hits in sources:
            for r in hits:
                cosine = 1.0 - r.distance
                if cosine >= NEAR_DUP_BASELINE:
                    continue
                promoted = promotable(r)
                if not promoted and cosine < CANDIDATE_FLOOR:
                    if report is not None and cosine > report.get("best_below_floor", -1.0):
                        report["best_below_floor"] = cosine
                        report["label"] = label
                    continue
                key = (r.type, r.doc_id)
                if key not in best or cosine > best[key][0]:
                    best[key] = (cosine, label, r, promoted)
    except Exception:
        return []
    own = exclude_path.resolve() if exclude_path else None
    out: list[Candidate] = []
    seen_notes: set[Path] = set()
    ranked = sorted(best.values(), key=lambda t: (not t[3], -t[0]))
    for cosine, label, r, promoted in ranked:
        note: Path | None
        try:
            if r.type == "video":
                if exclude_media_id and r.doc_id == exclude_media_id:
                    continue
                if exclude_url and r.source == exclude_url:
                    continue
                note = vault.find_note_by_url(r.source, 0.0)
            else:
                note = Path(r.source) if r.source else None
                if note is not None and not note.exists():
                    note = None
        except Exception:
            continue
        if note is None or not _linkable(note, brain):
            continue
        if exclude_targets and note.stem in exclude_targets:
            continue
        resolved = note.resolve()
        if resolved == own or resolved in seen_notes:
            continue
        if exclude_url and r.type != "video" and _note_url(note) == exclude_url:
            continue
        seen_notes.add(resolved)
        # A memory hit's title is its doc id; the stem reads better when the
        # note itself names nothing.
        fallback_title = r.title if r.type == "video" else note.stem
        title, thesis = _note_identity(note, fallback_title, r.excerpt)
        out.append(
            Candidate(
                target=note.stem,
                target_title=title,
                thesis=thesis,
                cosine=1.0 if promoted else cosine,
                via=TAKE_LABEL if promoted else label,
                path=str(resolved),
            )
        )
        if len(out) >= MAX_CANDIDATES:
            break
    return out


class Neighbour(BaseModel):
    """A nearby note as the enricher reads it: name, thesis, the owner's take."""

    target: str
    title: str
    thesis: str
    take: str | None = None
    cosine: float


SOURCE_LABEL = "the source"
# A first attempt has no thesis yet: title and the head of the caption,
# description or article stand in for it.
_SEED_CHARS = 600
_NEIGHBOUR_FIELD_CHARS = 400


def neighbour_queries(
    *,
    title: str | None,
    source_text: str | None,
    take: str | None,
    previous: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """The connect queries when a draft exists (retry: its thesis and
    concepts); otherwise the take and a seed cut from the source."""
    if previous and str(previous.get("thesis") or "").strip():
        concepts = cast("list[str]", previous.get("key_concepts") or [])
        return build_queries(str(previous["thesis"]), concepts, take)
    out: list[tuple[str, str]] = []
    if take and take.strip():
        out.append((TAKE_LABEL, take.strip()))
    seed = " ".join(x.strip() for x in (title, source_text) if x and x.strip())[:_SEED_CHARS]
    if seed:
        out.append((SOURCE_LABEL, seed))
    return out


def _note_take(note: Path) -> str | None:
    try:
        text = note.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^## My take\s*\n+(.+?)(?:\n## |\Z)", text, re.MULTILINE | re.DOTALL)
    return " ".join(m.group(1).split())[:_NEIGHBOUR_FIELD_CHARS] if m else None


def vault_neighbours(
    queries: list[tuple[str, str]],
    *,
    take: str | None,
    exclude_media_id: str | None,
    exclude_url: str | None,
) -> list[Neighbour]:
    """Up to MAX_CANDIDATES notes for the enricher to argue with: the
    take's named notes first, then the store's, through connect's band,
    exclusions and linkable rules. Reads only; never raises."""
    try:
        reading = read_take(take)
        found = find_candidates(
            queries,
            exclude_media_id=exclude_media_id,
            exclude_url=exclude_url,
            promote=reading.promote,
        )
        cands = merge_candidates(reading.named, found)
    except Exception:
        return []
    return [
        Neighbour(
            target=c.target,
            title=c.target_title,
            thesis=" ".join(c.thesis.split())[:_NEIGHBOUR_FIELD_CHARS],
            take=_note_take(Path(c.path)) if c.path else None,
            cosine=round(c.cosine, 3),
        )
        for c in cands
    ]


def linked_targets(text: str) -> set[str]:
    """Basenames the note already links to; Obsidian resolves [[a/b]] by b.
    Embeds (![[image.jpg]]) are media, not links."""
    return {
        m.group(1).strip().rsplit("/", 1)[-1]
        for m in _WIKILINK.finditer(text)
        if m.start() == 0 or text[m.start() - 1] != "!"
    }


def nearby(note: Path) -> list[Candidate]:
    """Layer 3 (the older notes): the note's doc-to-doc neighbours alone,
    through connect's band, unlinkable rules and cap, minus what it already
    links. Reads only; empty when the note has no stored vector."""
    try:
        text = note.read_text(encoding="utf-8")
    except OSError:
        return []
    from .hydrate import youtube_video_id

    url = _note_url(note)
    media_id = youtube_video_id(url) if url else None
    vector = own_vector(note, media_id)
    if vector is None:
        return []
    return find_candidates(
        [],
        exclude_media_id=media_id,
        exclude_url=url,
        exclude_path=note,
        vector=vector,
        exclude_targets=linked_targets(text),
    )


_ARGUE_SYSTEM = """You connect notes in a personal knowledge vault.

Given a new note's thesis and summary, and a numbered list of candidate
notes, return the links worth making. For each link give ONE clause (not a
sentence chain) arguing why the two notes belong together, tied to the new
note's thesis. Each candidate names the part of the new note it matched on
(the thesis, one key concept, or the owner's take); build the argument from
that part when it holds, and drop the candidate when the match is only the
word. A candidate the owner's take names outright is theirs to keep: argue
it in their terms. A candidate you cannot argue in one clause is omitted,
not padded. Returning no links is a fine answer."""

_ARGUE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "argument": {"type": "string"},
                },
                "required": ["target", "argument"],
            },
        }
    },
    "required": ["links"],
}

ARGUE_PROMPT_VERSION = hashlib.sha256(
    (_ARGUE_SYSTEM + json.dumps(_ARGUE_SCHEMA, sort_keys=True)).encode()
).hexdigest()[:12]


def _argue(
    thesis: str, summary: str, candidates: list[Candidate], take: str | None = None
) -> tuple[list[ProposedLink], Any]:
    from . import sdk

    lines = [f"New note thesis: {thesis}", f"Summary: {summary}"]
    if take and take.strip():
        lines.append(f"Owner's take: {take.strip()}")
    lines += ["", "Candidates:"]
    for i, c in enumerate(candidates, start=1):
        lines.append(
            f"{i}. target={c.target} · {c.target_title} · matched on: {c.via} · thesis: {c.thesis}"
        )
    res = sdk.call_structured(
        _ARGUE_SYSTEM, "\n".join(lines), _ARGUE_SCHEMA, model=CONNECT_MODEL, max_turns=4
    )
    by_target = {c.target: c for c in candidates}
    links: list[ProposedLink] = []
    raw_obj: object = res.data.get("links")
    raw_links = cast("list[object]", raw_obj) if isinstance(raw_obj, list) else []
    for raw_any in raw_links:
        if not isinstance(raw_any, dict):
            continue
        raw = cast("dict[str, Any]", raw_any)
        target = str(raw.get("target", ""))
        cand = by_target.get(target)
        # The model picks from the list; an invented target is dropped.
        argument = raw.get("argument")
        if cand is None or not argument:
            continue
        links.append(
            ProposedLink(target=target, target_title=cand.target_title, argument=str(argument))
        )
    return links, res


def propose(
    conn: sqlite3.Connection,
    item_id: int,
    thesis: str,
    summary: str,
    *,
    exclude_media_id: str | None,
    exclude_url: str | None = None,
    note_path: Path | None = None,
    key_concepts: list[str] | None = None,
    take: str | None = None,
    actor: str = "connect",
) -> int | None:
    """Find candidates, argue them, raise the connections ask. Returns the
    ask id, or None when there is nothing worth asking about. Never writes
    the vault."""
    from . import loop

    loop.stamp_stage("connect", "finding candidates")
    reading = read_take(take, exclude_path=note_path)
    report: dict[str, Any] = {}
    found = find_candidates(
        build_queries(thesis, key_concepts, take),
        exclude_media_id=exclude_media_id,
        exclude_url=exclude_url,
        exclude_path=note_path,
        promote=reading.promote,
        report=report,
        vector=own_vector(note_path, exclude_media_id),
    )
    candidates = merge_candidates(reading.named, found)
    if not candidates:
        reason = "no candidates in band"
        if "best_below_floor" in report:
            reason += f"; best below floor {report['best_below_floor']:.3f} via {report['label']}"
        else:
            reason += "; no hits at all"
        ledger.insert_activity(conn, item_id, actor=actor, action="connect", reason=reason)
        return None
    loop.stamp_stage("connect", f"arguing {len(candidates)} candidates")
    links, res = _argue(thesis, summary, candidates, take)
    ledger.insert_activity(
        conn,
        item_id,
        actor=actor,
        action="connect",
        inputs=json.dumps({"prompt_version": ARGUE_PROMPT_VERSION}),
        model=res.model,
        tokens=res.tokens,
        duration_ms=res.duration_ms,
        reason=f"{len(links)} of {len(candidates)} candidates argued",
        detail=json.dumps(
            {
                "links": [link.model_dump() for link in links],
                "candidates": [
                    {"target": c.target, "via": c.via, "cosine": round(c.cosine, 3)}
                    for c in candidates
                ],
            }
        ),
    )
    if not links:
        return None
    return asks.raise_ask(
        conn,
        item_id,
        proposal={
            "kind": "connections",
            "why": f"{len(links)} related notes argued",
            "options": ["approve", "strike some", "none"],
            "links": [link.model_dump() for link in links],
        },
        actor=actor,
    )


def write_links(
    conn: sqlite3.Connection, item_id: int, path: Path, links: list[ProposedLink]
) -> str:
    """The one vault write for approved links, from the ask or the nearby
    tap: snapshot, merge into `## Connections`, re-index. Returns the
    re-index outcome."""
    from . import notes

    notes.snapshot_note(conn, item_id, path)
    notes.add_connections(path, [(link.target, link.argument) for link in links])
    return notes.reindex_connected(path)


class NearbyRefused(ValueError):
    """A tap that cannot be applied as asked; nothing was written."""


class NearbyLink(BaseModel):
    target: str
    target_title: str
    cosine: float
    argument: str  # BY_HAND when no clause was argued
    reindex: str | None = None


# The owner's tap is the judgment; this clause stands in when the model argues none.
BY_HAND = "linked by hand"


def _note_section(text: str, heading: str) -> str:
    m = re.search(
        rf"^## {re.escape(heading)}\s*\n+(.+?)(?:\n## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    return m.group(1).strip() if m else ""


def _hold(conn: sqlite3.Connection, item_id: int) -> str | None:
    """The loop's lease, taken without counting a tick: the loop and a tap
    never write one note at once. A crashed holder's lease expires."""
    from datetime import UTC, datetime, timedelta

    from .loop import LEASE_MINUTES

    now = datetime.now(UTC)
    until = (now + timedelta(minutes=LEASE_MINUTES)).isoformat()
    cur = conn.execute(
        "UPDATE items SET lease_until = ? WHERE id = ? AND (lease_until IS NULL OR lease_until < ?)",
        (until, item_id, now.isoformat()),
    )
    conn.commit()
    return until if cur.rowcount else None


def link_nearby(conn: sqlite3.Connection, note: Path, target: str, *, surface: str) -> NearbyLink:
    """The owner tapped a nearby note: argue the clause (one model call),
    write the link through write_links, and record the tap as the owner's
    judgment. The tap always writes: a declined or failed argue writes the
    link with BY_HAND. Refuses a note the ledger never took in and a target
    that is no longer nearby."""
    from . import vault

    clicked_at = ledger.now()
    item_id = ledger.item_for_note(conn, note, vault.get_brain_path())
    if item_id is None:
        raise NearbyRefused("this note has no ledger item, so a link here has no record to live in")
    cand = next((c for c in nearby(note) if c.target == target), None)
    if cand is None:
        raise NearbyRefused(f"[[{target}]] is not among this note's nearby notes any more")
    held = _hold(conn, item_id)
    if held is None:
        raise NearbyRefused("the curator loop is working on this note; try again in a minute")
    link = ProposedLink(target=cand.target, target_title=cand.target_title, argument=BY_HAND)
    reindexed: str | None = None
    argue_error: str | None = None
    failure: str | None = None
    try:
        try:
            text = note.read_text(encoding="utf-8")
            _, thesis = _note_identity(note, note.stem, "")
            summary = _note_section(text, "Commentary") or _note_section(text, "Summary")
            links, res = _argue(thesis, summary, [cand], _note_take(note))
        except Exception as exc:
            argue_error = f"{type(exc).__name__}: {exc}"[:200]
        else:
            ledger.insert_activity(
                conn,
                item_id,
                actor="connect",
                action="connect",
                inputs=json.dumps({"prompt_version": ARGUE_PROMPT_VERSION}),
                model=res.model,
                tokens=res.tokens,
                duration_ms=res.duration_ms,
                reason=f"{len(links)} of 1 candidates argued (nearby tap)",
                detail=json.dumps(
                    {
                        "links": [argued.model_dump() for argued in links],
                        "candidates": [
                            {
                                "target": cand.target,
                                "via": cand.via,
                                "cosine": round(cand.cosine, 3),
                            }
                        ],
                        "trigger": "nearby",
                    }
                ),
            )
            if links:
                link = links[0]
        reindexed = write_links(conn, item_id, note, [link])
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"[:200]
        raise
    finally:
        conn.execute(
            "UPDATE items SET lease_until = NULL WHERE id = ? AND lease_until = ?", (item_id, held)
        )
        conn.commit()
        if failure:
            reason = f"owner picked [[{target}]] from nearby; failed before the write landed"
        elif argue_error:
            reason = f"owner linked [[{target}]] from nearby by hand; the argue call failed"
        elif link.argument == BY_HAND:
            reason = f"owner linked [[{target}]] from nearby by hand; no clause argued"
        else:
            reason = f"owner linked [[{target}]] from nearby"
        ledger.insert_activity(
            conn,
            item_id,
            actor="owner",
            action="nearby-link",
            output_ref=None if failure else str(note),
            reason=reason,
            detail=json.dumps(
                {
                    "target": target,
                    "cosine": round(cand.cosine, 3),
                    "surface": surface,
                    "argument": None if failure else link.argument,
                    "reindex": reindexed,
                    "error": failure or argue_error,
                }
            ),
            at=clicked_at,
        )
    return NearbyLink(
        target=target,
        target_title=cand.target_title,
        cosine=round(cand.cosine, 3),
        argument=link.argument,
        reindex=reindexed,
    )


def apply_links(conn: sqlite3.Connection, item_id: int, *, actor: str = "loop") -> None:
    """Apply the owner's connections answer (loop-dispatched, single writer):
    none returns the item to kept and writes nothing; approve / strike-some
    snapshots the landed note and writes the survivors. Idempotent under a
    lease-expiry re-run — the section write is a whole-section replace, and
    a duplicate snapshot row is a harmless extra undo."""
    from pathlib import Path

    row = conn.execute(
        """
        SELECT asks.proposal, answers.choice, answers.text FROM asks
        JOIN answers ON answers.ask_id = asks.id
        WHERE asks.item_id = ? AND asks.kind = 'connections'
        ORDER BY answers.id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("no answered connections ask")
    proposal = cast("dict[str, Any]", json.loads(row["proposal"]))
    raw_links = cast("list[Any]", proposal.get("links") or [])
    links = [ProposedLink.model_validate(raw) for raw in raw_links]
    choice = str(row["choice"])

    survivors = links
    reason = f"owner: {choice}"
    if choice == "none":
        survivors = []
    elif choice == "strike some":
        keep: set[str] = set()
        try:
            keep = set(asks.strike_some_survivors(raw_links, row["text"]))
        except asks.AnswerRefused:
            # Recorded before answers were checked (ask 87); applies as none.
            reason = "owner: strike some, answer unreadable (not a JSON list of targets)"
        survivors = [link for link in links if link.target in keep]

    from_state = ledger.item_state(conn, item_id)
    if not survivors:
        ledger.insert_activity(
            conn,
            item_id,
            actor=actor,
            action="connect-none",
            from_state=from_state,
            to_state="kept",
            reason=reason,
        )
        return

    note_row = conn.execute(
        """
        SELECT output_ref FROM activity
        WHERE item_id = ? AND action = 'keep' AND output_ref IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    if note_row is None or not Path(note_row["output_ref"]).exists():
        raise RuntimeError("no landed note on disk to connect")
    path = Path(note_row["output_ref"])
    reindexed = write_links(conn, item_id, path, survivors)
    ledger.insert_activity(
        conn,
        item_id,
        actor=actor,
        action="connect-apply",
        from_state=from_state,
        to_state="connected",
        output_ref=str(path),
        reason=f"owner approved {len(survivors)} of {len(links)} links",
        detail=json.dumps(
            {"links": [link.model_dump() for link in survivors], "reindex": reindexed}
        ),
    )
