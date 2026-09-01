"""The connect verb (#197 P6): an accepted note gets proposed links, each
with a one-clause argument tied to the thesis. Writes nothing to the vault
— the owner approves at the digest, and only the loop applies survivors
(snapshot first). AI links are worthless unless the owner made them; bulk
generated links degrade search (spec, What the research says).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, cast

from pydantic import BaseModel

from . import asks, ledger

# Candidate band, re-sized from strike/approve answers over time. Floor:
# measured 2026-08-31 on the production path (thesis+summary through the
# instruction-aware QUERY embedding, 12 sampled notes vs the 442-vector
# corpus): top-1 neighbor cosine median 0.468, max 0.688; background tops
# out ~0.53 while clearly related pairs read 0.63+. The doc-doc scale
# (NN p50 0.560) does NOT transfer to this path — 0.60 here would mute
# connect for most notes. Ceiling: NEAR_DUP_BASELINE, which on this path
# never binds (max observed 0.688 between distinct videos); kept as the
# formal dup boundary.
CANDIDATE_FLOOR = 0.55
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


class ProposedLink(BaseModel):
    target: str
    target_title: str
    argument: str


def find_candidates(query: str, *, exclude_media_id: str | None) -> list[Candidate]:
    """Neighbors in the band [CANDIDATE_FLOOR, NEAR_DUP_BASELINE), resolved
    to vault notes, capped. The one transport seam kernel 1 replaces in P7;
    None-tolerant when the store is down (no candidates, never a failure)."""
    from .grader import NEAR_DUP_BASELINE

    try:
        from . import store, vault

        results = store.search_videos(query, n=_FETCH_N, rerank=False, actor="connect")
    except Exception:
        return []
    out: list[Candidate] = []
    for r in results:
        if exclude_media_id and r.video_id == exclude_media_id:
            continue
        cosine = 1.0 - r.distance
        if cosine >= NEAR_DUP_BASELINE or cosine < CANDIDATE_FLOOR:
            continue
        try:
            note = vault.find_note_by_url(r.url, 0.0)
        except Exception:
            continue
        if note is None:
            continue
        out.append(
            Candidate(target=note.stem, target_title=r.title, thesis=r.thesis, cosine=cosine)
        )
        if len(out) >= MAX_CANDIDATES:
            break
    return out


_ARGUE_SYSTEM = """You connect notes in a personal knowledge vault.

Given a new note's thesis and summary, and a numbered list of candidate
notes, return the links worth making. For each link give ONE clause (not a
sentence chain) arguing why the two notes belong together, tied to the new
note's thesis. A candidate you cannot argue in one clause is omitted, not
padded. Returning no links is a fine answer."""

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
    thesis: str, summary: str, candidates: list[Candidate]
) -> tuple[list[ProposedLink], Any]:
    from . import sdk

    lines = [f"New note thesis: {thesis}", f"Summary: {summary}", "", "Candidates:"]
    for i, c in enumerate(candidates, start=1):
        lines.append(f"{i}. target={c.target} · {c.target_title} · thesis: {c.thesis}")
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
    actor: str = "connect",
) -> int | None:
    """Find candidates, argue them, raise the connections ask. Returns the
    ask id, or None when there is nothing worth asking about. Never writes
    the vault."""
    from . import loop

    loop.stamp_stage("connect", "finding candidates")
    candidates = find_candidates(f"{thesis}\n\n{summary}", exclude_media_id=exclude_media_id)
    if not candidates:
        ledger.insert_activity(
            conn, item_id, actor=actor, action="connect", reason="no candidates in band"
        )
        return None
    loop.stamp_stage("connect", f"arguing {len(candidates)} candidates")
    links, res = _argue(thesis, summary, candidates)
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
        detail=json.dumps({"links": [link.model_dump() for link in links]}),
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
    if choice == "none":
        survivors = []
    elif choice == "strike some":
        keep: set[str] = set()
        if row["text"]:
            try:
                parsed: object = json.loads(row["text"])
            except ValueError:
                parsed = None
            if isinstance(parsed, list):
                keep = {str(t) for t in cast("list[object]", parsed)}
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
            reason=f"owner: {choice}",
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

    from . import notes

    notes.snapshot_note(conn, item_id, path)
    notes.apply_connections(path, [(link.target, link.argument) for link in survivors])
    ledger.insert_activity(
        conn,
        item_id,
        actor=actor,
        action="connect-apply",
        from_state=from_state,
        to_state="connected",
        output_ref=str(path),
        reason=f"owner approved {len(survivors)} of {len(links)} links",
        detail=json.dumps({"links": [link.model_dump() for link in survivors]}),
    )
