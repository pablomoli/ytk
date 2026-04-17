"""ytk MCP server — exposes vault + vector store to Claude Code sessions."""

from __future__ import annotations

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

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
        lines.append(
            f"[{r.type}] {r.title}  ({match_pct} match)\n"
            f"{r.excerpt}\n"
            f"source: {r.source}"
        )
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
    """Write or overwrite a note at a vault path (relative to vault root)."""
    from .vault import write_raw

    note_path = write_raw(path, content)
    return f"Written: {note_path}"


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


def main() -> None:
    app.run()
