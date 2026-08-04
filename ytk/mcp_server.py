# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""ytk MCP server for Codex and Claude Code sessions."""

from __future__ import annotations

import re
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path.home() / ".ytk" / ".env")
load_dotenv()

app = FastMCP("ytk")


@app.tool()
def vault_search(query: str, n: int = 5) -> str:
    """Semantic search across all vault content (videos and memories)."""
    from .store import search_all

    results = search_all(query, n=n)
    if not results:
        return "No results found."

    lines: list[str] = []
    for r in results:
        match_pct = f"{(1 - r.distance):.0%}"
        lines.append(f"[{r.type}] {r.title}  ({match_pct} match)\n{r.excerpt}\nsource: {r.source}")
    return "\n\n".join(lines)


@app.tool()
def vault_read(path: str) -> str:
    """Read a vault note by relative path from the vault root (e.g.
    'projects/ytk/session-001-brief.md'). For the full vault index, read
    'wiki/index.md'."""
    from .vault import read_note

    return read_note(path)


@app.tool()
def vault_write(path: str, content: str) -> str:
    """Write or overwrite a note at a vault path and index it in ChromaDB for search."""
    from .cache import load_index_cache, save_index_cache, update_cache_entry
    from .store import live_slice, strip_frontmatter, upsert_doc
    from .vault import write_raw

    note_path = write_raw(path, content)
    _id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
    doc_id = (
        _id_match.group(1).strip()
        if _id_match
        else "note_" + path.replace("/", "_").replace(".md", "").replace(" ", "_")
    )
    body = live_slice(strip_frontmatter(content))
    parts = path.split("/")
    tags = parts[:-1]
    upsert_doc(
        doc_id,
        body,
        {
            "doc_id": doc_id,
            "tags": ", ".join(tags),
            "source_path": str(note_path),
        },
    )
    cache = load_index_cache()
    update_cache_entry(note_path, cache)
    save_index_cache(cache)
    return f"Written and indexed: {note_path}"


@app.tool()
def vault_remember(text: str, tags: list[str] | None = None, update_path: str | None = None) -> str:
    """Store arbitrary text as an atomic memory note and index it for semantic search.

    The result lists similar existing memories (R1/#150) — if one already covers
    this, pass its brain-relative path as update_path to append there instead of
    creating a near-duplicate. Nothing is ever merged or deleted automatically.
    """
    from .store import live_slice, similar_memories, strip_frontmatter, upsert_doc, upsert_memory
    from .vault import append_to_note, remember

    if update_path:
        note_path = append_to_note(update_path, text)
        content = note_path.read_text(encoding="utf-8")
        _id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
        doc_id = (
            _id_match.group(1).strip()
            if _id_match
            else "note_" + update_path.replace("/", "_").replace(".md", "").replace(" ", "_")
        )
        upsert_doc(
            doc_id,
            live_slice(strip_frontmatter(content)),
            {"doc_id": doc_id, "tags": ", ".join(tags or []), "source_path": str(note_path)},
        )
        return f"Appended to existing memory: {note_path}"

    # neighbors are queried before the write so the new note can't shadow them
    neighbors = similar_memories(text, n=5)
    note_path, doc_id = remember(text, tags or [])
    upsert_memory(doc_id, text, tags or [], str(note_path))
    out = f"Memory stored: {note_path}"
    close = [nb for nb in neighbors if nb.similarity >= 0.60]
    if close:
        out += "\n\nSimilar existing memories (pass update_path to append there instead):"
        for nb in close:
            out += f"\n  {nb.similarity:.0%}  {nb.source_path}\n      {nb.excerpt[:120]}"
    return out


@app.tool()
def vault_update_index() -> str:
    """Regenerate wiki/index.md by scanning the entire vault from scratch."""
    from .vault import rebuild_index

    rebuild_index()
    return "Index rebuilt."


@app.tool()
def vault_reindex(force: bool = False) -> str:
    """Scan and index all vault notes into ChromaDB. Set force=True to bypass cache and re-embed everything."""
    from .vault import reindex_vault

    count = reindex_vault(force=force)
    return f"Indexed {count} notes."


@app.tool()
def vault_search_index(query: str, n: int = 10) -> str:
    """Index-only semantic search: match%, type, doc id, capture date — no
    excerpts. Fetch full text for chosen ids with vault_fetch (E2/#149)."""
    from .store import memory_captured_at, search_all

    results = search_all(query, n=n)
    if not results:
        return "No results found."
    return "\n".join(
        f"{(1 - r.distance):.0%}  [{r.type}] {r.doc_id}  "
        f"{memory_captured_at(None, r.doc_id) or '-'}"
        for r in results
    )


@app.tool()
def vault_fetch(ids: list[str]) -> str:
    """Fetch stored document text for explicit doc ids (from vault_search_index).

    Returns the embedded text, not the raw file — video notes' transcripts
    stay out of context unless you vault_read the note deliberately."""
    from .store import fetch_docs

    docs = fetch_docs(ids)
    if not docs:
        return "No documents found for those ids."
    return "\n\n".join(f"=== {doc_id} ===\n{text}" for doc_id, text in docs)


@app.tool()
def work_list() -> str:
    """List active ytk GitHub Project items in canonical order."""
    from .workboard import format_queue, get_snapshot

    return format_queue(get_snapshot())


@app.tool()
def work_next() -> str:
    """Show ytk work already in progress and the next executable ticket."""
    from .workboard import format_snapshot, get_snapshot

    return format_snapshot(get_snapshot())


@app.tool()
def work_set_stage(issue_number: int, stage: str) -> str:
    """Explicitly change a ytk issue's GitHub Project Stage."""
    from .workboard import set_issue_stage

    updated = set_issue_stage(issue_number, stage)
    return f"Updated #{updated.number} to {updated.stage}."


@app.tool()
def work_audit(fix: bool = False) -> str:
    """Reconcile the ytk Project board against issue state in both directions:
    open issues missing from the board, rows with empty fields, and rows whose
    issue is closed. fix=True archives the closed-issue rows."""
    from .workboard import archive_board_ghosts, audit_board, format_audit

    missing, incomplete, ghosts = audit_board()
    prefix = ""
    if fix and ghosts:
        archived = archive_board_ghosts()
        numbers = ", ".join(f"#{item.number}" for item in archived)
        prefix = f"Archived {len(archived)} ghost rows: {numbers}\n"
        ghosts = ()
    return prefix + format_audit(missing, incomplete, ghosts)


@app.tool()
def work_set_fields(
    issue_number: int,
    kind: str | None = None,
    priority: str | None = None,
    area: str | None = None,
    stage: str | None = None,
    order: float | None = None,
    create: bool = False,
) -> str:
    """Set any subset of a ytk issue's Project fields. Set create=True to add it to the board first.

    kind: bug, ux-debt, feature, investigation, maintenance, initiative.
    priority: p0-p3. area: hub-ui, capture-and-ingest, retrieval-and-eval,
    map-growth-and-grove, vault, platform, research.
    stage: triage, needs-evidence, ready, in-progress, verify, done.
    """
    from .workboard import set_issue_fields

    updated = set_issue_fields(
        issue_number,
        kind=kind,
        priority=priority,
        area=area,
        stage=stage,
        order=order,
        create=create,
    )
    return (
        f"#{updated.number}: kind={updated.kind or '-'} priority={updated.priority or '-'} "
        f"area={updated.area or '-'} stage={updated.stage or '-'} order={updated.order:g}"
    )


def main() -> None:
    app.run()
