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
    """Read a vault note by relative path from the vault root (e.g. 'projects/ytk/session-001-brief.md')."""
    from .vault import read_note

    return read_note(path)


@app.tool()
def vault_list() -> str:
    """Return the current wiki/index.md contents — a structured index of all vault content."""
    from .vault import list_index

    return list_index()


@app.tool()
def vault_write(path: str, content: str) -> str:
    """Write or overwrite a note at a vault path and index it in ChromaDB for search."""
    from .cache import load_index_cache, save_index_cache, update_cache_entry
    from .store import strip_frontmatter, upsert_doc
    from .vault import write_raw

    note_path = write_raw(path, content)
    _id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
    doc_id = (
        _id_match.group(1).strip()
        if _id_match
        else "note_" + path.replace("/", "_").replace(".md", "").replace(" ", "_")
    )
    body = strip_frontmatter(content)
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
def vault_remember(text: str, tags: list[str] | None = None) -> str:
    """Store arbitrary text as an atomic memory note and index it for semantic search."""
    from .store import upsert_memory
    from .vault import remember

    note_path, doc_id = remember(text, tags or [])
    upsert_memory(doc_id, text, tags or [], str(note_path))
    return f"Memory stored: {note_path}"


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
def visual_similar(query: str, n: int = 8) -> str:
    """Visually similar saves via SigLIP-2. QUERY may be a stored item id
    (yt:<video_id>, ig:<shortcode>, tt:<id>, cover:<hash>), an absolute image
    path, or a free-text description (uses the text tower)."""
    import os

    from . import visual as vis
    from .store import get_visual_embedding
    from .store import visual_similar as _similar

    item_id = None
    embedding = None
    if get_visual_embedding(query) is not None:
        item_id = query
    elif os.path.isabs(query) and os.path.exists(query):
        from pathlib import Path

        embedding = vis.embed_images([Path(query)])[0]
    else:
        embedding = vis.embed_text(query)

    results = _similar(item_id=item_id, embedding=embedding, n=n)
    if not results:
        return "No matches. Has `ytk visual index` been run?"
    lines = []
    for r in results:
        label = r.title or r.item_id
        lines.append(f"[{r.distance:.3f}] {label} ({r.source}) {r.url or r.image_path}")
    return "\n".join(lines)


def main() -> None:
    app.run()
