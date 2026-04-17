# Shared Brain Sprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the write-path and lifecycle gaps in the ytk shared brain so every Claude session, user terminal action, and web article automatically feeds the vault.

**Architecture:** Seven targeted additions — store primitives enabling generic doc indexing, vault.py extensions for web notes and bulk reindex, a new `ytk/ingest.py` module for web fetch+enrich, four new CLI commands, two MCP tool fixes, a global CLAUDE.md session-end rule, and a Stop hook that re-seeds the active project's vault memory after every session.

**Tech Stack:** Python 3.11+, uv, Click, FastMCP, ChromaDB, Claude Haiku (claude-haiku-4-5), trafilatura, Rich

**Parallel opportunities:** Tasks 1+2 are independent and can run simultaneously. Tasks 3+4 can run after Task 1. Tasks 5+6 can run after Tasks 3+4. Task 7 is independent of Tasks 3-6.

---

### Task 1: Store primitives — strip_frontmatter, upsert_doc, delete_doc

**Files:**
- Modify: `ytk/store.py`

- [ ] **Add `strip_frontmatter` and `upsert_doc` above `upsert_memory`**

Insert after the `_memories_collection` function definition (after line 70 currently):

```python
def strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter block from markdown so only body text is indexed."""
    if not text.startswith("---"):
        return text
    end = text.find("---", 3)
    return text[end + 3:].lstrip() if end != -1 else text


def upsert_doc(doc_id: str, text: str, metadata: dict) -> None:
    """Upsert arbitrary text into the memories collection."""
    _memories_collection().upsert(
        ids=[doc_id],
        documents=[text[:8000]],
        metadatas=[metadata],
    )


def delete_doc(doc_id: str) -> None:
    """Remove a document from the memories collection by ID."""
    try:
        _memories_collection().delete(ids=[doc_id])
    except Exception:
        pass
```

- [ ] **Refactor `upsert_memory` to delegate to `upsert_doc`**

Replace the existing `upsert_memory` body:

```python
def upsert_memory(doc_id: str, text: str, tags: list[str], source_path: str) -> None:
    """Embed and store an arbitrary memory note in the ytk_memories collection."""
    upsert_doc(doc_id, text, {
        "doc_id": doc_id,
        "tags": ", ".join(tags),
        "source_path": source_path,
    })
```

- [ ] **Verify imports are clean**

```bash
uv run python -c "from ytk.store import strip_frontmatter, upsert_doc, delete_doc, upsert_memory, search_all; print('store OK')"
```

Expected: `store OK`

- [ ] **Commit**

```bash
git add ytk/store.py
git commit -m "feat(store): add upsert_doc, delete_doc, strip_frontmatter primitives"
```

---

### Task 2: Global session-end capture rule in CLAUDE.md

**Files:**
- Modify: `~/.claude/CLAUDE.md`

- [ ] **Append the shared brain rule**

Read `~/.claude/CLAUDE.md` and append:

```markdown

## Shared brain (ytk vault)

The ytk MCP server is registered globally. `vault_remember` is available in every project.

At the end of any session where significant decisions, architectural choices, or non-obvious learnings occurred, call `vault_remember` with a concise summary (2-5 sentences). Tag it with the project name (e.g. `["epicmap", "auth"]`). Err on the side of capturing — a short redundant note costs nothing; a lost decision costs a future session.
```

Note: `~/.claude/CLAUDE.md` is a global config file, not in the ytk git repo. Just write it — no commit.

---

### Task 3: vault.py — id: frontmatter, write_web_note, reindex_vault

**Files:**
- Modify: `ytk/vault.py`

**Depends on:** Task 1 (needs `upsert_doc`, `strip_frontmatter` from store.py)

- [ ] **Update `remember()` to write `id:` into frontmatter**

Replace the `note_path.write_text(...)` call inside `remember()`:

```python
    note_path.write_text(
        f"---\nid: {doc_id}\ndate: {date_str}\ntags:\n{tags_yaml}\ntype: memory\n---\n\n{text}\n",
        encoding="utf-8",
    )
```

- [ ] **Add `write_web_note()` after `remember()`**

```python
def write_web_note(url: str, title: str, author: str, date: str, enrichment: Enrichment) -> Path:
    """Write an Obsidian note for an ingested web article. Returns the path written."""
    vault_path = _get_vault_path()
    note_dir = vault_path / "sources" / "web"
    note_dir.mkdir(parents=True, exist_ok=True)

    filename = _slug(title)
    note_path = note_dir / f"{filename}.md"

    def _normalize_tag(t: str) -> str:
        return re.sub(r"\s+", "-", t.strip().lower())

    tags_yaml = "\n".join(f"  - {_normalize_tag(t)}" for t in enrichment.interest_tags)
    concepts = "\n".join(f"- {c}" for c in enrichment.key_concepts)
    insights = "\n".join(f"- {i}" for i in enrichment.insights)

    note_path.write_text(
        f"---\nurl: {url}\ntitle: {title}\nauthor: {author}\ndate: {date}\ntags:\n{tags_yaml}\ntype: web\n---\n\n"
        f"## Thesis\n{enrichment.thesis}\n\n"
        f"## Summary\n{enrichment.summary}\n\n"
        f"## Key Concepts\n{concepts}\n\n"
        f"## Insights\n{insights}\n",
        encoding="utf-8",
    )
    return note_path
```

- [ ] **Add `reindex_vault()` after `write_web_note()`**

```python
def reindex_vault() -> int:
    """
    Scan vault directories and bulk-upsert all .md files into ChromaDB.
    Skips sources/youtube/ (indexed separately by store.upsert).
    Returns count of notes indexed.
    """
    from .store import upsert_doc, strip_frontmatter

    vault_path = _get_vault_path()
    scan_dirs = ["inbox/memories", "inbox", "projects", "decisions", "debugging", "tools"]
    seen_paths: set[str] = set()
    count = 0

    for subdir in scan_dirs:
        d = vault_path / subdir
        if not d.exists():
            continue
        pattern = "*.md" if subdir == "inbox" else "**/*.md"
        for md_file in d.glob(pattern):
            str_path = str(md_file)
            if str_path in seen_paths:
                continue
            seen_paths.add(str_path)
            rel = md_file.relative_to(vault_path)
            doc_id = "note_" + str(rel).replace("/", "_").replace(".md", "").replace(" ", "_")
            content = md_file.read_text(encoding="utf-8")
            body = strip_frontmatter(content)
            if not body.strip():
                continue
            parts = str(rel).split("/")
            tags = parts[:-1]
            upsert_doc(doc_id, body, {
                "doc_id": doc_id,
                "tags": ", ".join(tags),
                "source_path": str_path,
            })
            count += 1

    return count
```

- [ ] **Verify**

```bash
uv run python -c "from ytk.vault import remember, write_web_note, reindex_vault; print('vault OK')"
```

Expected: `vault OK`

- [ ] **Commit**

```bash
git add ytk/vault.py
git commit -m "feat(vault): add id: frontmatter, write_web_note, reindex_vault"
```

---

### Task 4: trafilatura dependency + ytk/ingest.py

**Files:**
- Modify: `pyproject.toml`
- Create: `ytk/ingest.py`

**Depends on:** Task 3 (imports `Enrichment` from enrich.py — actually independent, just needs enrich.py which already exists)

- [ ] **Add trafilatura to pyproject.toml**

In the `dependencies` list, add after `mcp>=1.0`:

```toml
    "trafilatura>=1.6",
```

- [ ] **Run uv sync**

```bash
uv sync
```

Expected: trafilatura and its deps appear in uv.lock output.

- [ ] **Create ytk/ingest.py**

```python
"""Web content ingestion — fetch and extract readable text from any URL."""

from __future__ import annotations

from dataclasses import dataclass

import trafilatura

from .enrich import Enrichment


_SYSTEM_WEB = """\
You are a research assistant helping build a personal knowledge library from web articles.
Return a JSON object with these fields:

thesis: One precise sentence capturing the article's main argument or finding. Never vague.

summary: 3-5 sentences for someone who wants a sharp reminder. Name specific tools,
  techniques, data, or findings concretely — not just topics.

key_concepts: Terms, tools, or techniques worth knowing. Format each as "name: how it was
  used or argued in this article". Max 8 items.

insights: 2-3 specific, actionable things worth remembering — non-obvious tradeoffs,
  surprising findings, or techniques that differ from conventional wisdom.

interest_tags: 3-8 lowercase hyphenated topic labels (e.g. "machine-learning", "go", "geospatial").

key_moments: Return an empty list [].
"""


@dataclass
class WebContent:
    url: str
    title: str
    author: str
    date: str
    text: str


def fetch_web(url: str) -> WebContent:
    """Fetch and extract readable text from a URL using trafilatura."""
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError(f"Could not fetch URL: {url}")

    metadata = trafilatura.extract_metadata(downloaded)
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)

    if not text:
        raise ValueError(f"Could not extract readable text from: {url}")

    return WebContent(
        url=url,
        title=metadata.title if metadata and metadata.title else url,
        author=metadata.author if metadata and metadata.author else "",
        date=metadata.date if metadata and metadata.date else "",
        text=text,
    )


def enrich_web(content: WebContent) -> Enrichment:
    """Summarize web article content using Claude Haiku. key_moments is always []."""
    import anthropic

    client = anthropic.Anthropic()
    user_content = (
        f"Title: {content.title}\nAuthor: {content.author}\n"
        f"Date: {content.date}\nURL: {content.url}\n\n"
        f"Article:\n{content.text[:6000]}"
    )

    response = client.messages.parse(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=[{"type": "text", "text": _SYSTEM_WEB, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
        output_format=Enrichment,
    )
    return response.parsed_output
```

- [ ] **Verify**

```bash
uv run python -c "from ytk.ingest import fetch_web, enrich_web, WebContent; print('ingest OK')"
```

Expected: `ingest OK`

- [ ] **Commit**

```bash
git add pyproject.toml uv.lock ytk/ingest.py
git commit -m "feat(ingest): add web content fetch + Haiku enrichment via trafilatura"
```

---

### Task 5: mcp_server.py — fix vault_write, add vault_reindex

**Files:**
- Modify: `ytk/mcp_server.py`

**Depends on:** Tasks 1 + 3

- [ ] **Replace `vault_write` tool with indexing version**

```python
@app.tool()
def vault_write(path: str, content: str) -> str:
    """Write or overwrite a note at a vault path and index it in ChromaDB for search."""
    from .store import upsert_doc, strip_frontmatter
    from .vault import write_raw

    note_path = write_raw(path, content)
    doc_id = "note_" + path.replace("/", "_").replace(".md", "").replace(" ", "_")
    body = strip_frontmatter(content)
    parts = path.split("/")
    tags = parts[:-1]
    upsert_doc(doc_id, body, {
        "doc_id": doc_id,
        "tags": ", ".join(tags),
        "source_path": str(note_path),
    })
    return f"Written and indexed: {note_path}"
```

- [ ] **Add `vault_reindex` tool after `vault_update_index`**

```python
@app.tool()
def vault_reindex() -> str:
    """Scan and index all vault notes (projects, decisions, inbox, etc.) into ChromaDB."""
    from .vault import reindex_vault

    count = reindex_vault()
    return f"Indexed {count} notes."
```

- [ ] **Verify server still loads**

```bash
uv run python -c "from ytk.mcp_server import app; print('mcp OK')"
```

Expected: `mcp OK`

- [ ] **Commit**

```bash
git add ytk/mcp_server.py
git commit -m "feat(mcp): vault_write now indexes to ChromaDB; add vault_reindex tool"
```

---

### Task 6: cli.py — ytk remember, ytk reindex, ytk ingest, ytk gc

**Files:**
- Modify: `ytk/cli.py`

**Depends on:** Tasks 1, 3, 4

- [ ] **Update top-level imports in cli.py**

The current imports block starts with `import os`. Ensure `import re`, `import sys`, and `timedelta` are present:

```python
import re
import sys
from datetime import datetime, timedelta
```

(`datetime` is already imported — add `timedelta` to that import. Add `re` and `sys` as new lines.)

- [ ] **Add `ytk remember` command** (insert before the `index_cmd` command)

```python
@cli.command(name="remember")
@click.argument("text", required=False, default="")
@click.option("--tags", "-t", default="", help="Comma-separated tags.")
def remember_cmd(text: str, tags: str):
    """Store a memory note in the vault and index it for semantic search.

    TEXT may be omitted to read from stdin: echo 'note' | ytk remember -t foo
    """
    from .store import upsert_memory
    from .vault import remember as _remember

    if not text:
        text = sys.stdin.read().strip()
    if not text:
        console.print("[red]No text provided.[/]")
        raise SystemExit(1)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        note_path, doc_id = _remember(text, tag_list)
        upsert_memory(doc_id, text, tag_list, str(note_path))
        console.print(f"[bold green]Memory stored:[/] {note_path}")
    except EnvironmentError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)
```

- [ ] **Add `ytk reindex` command** (after `remember_cmd`)

```python
@cli.command(name="reindex")
def reindex_cmd():
    """Index all vault notes into ChromaDB for semantic search."""
    from .vault import _get_vault_path, reindex_vault

    try:
        _get_vault_path()
    except EnvironmentError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    with console.status("[bold cyan]Indexing vault notes...[/]"):
        count = reindex_vault()

    console.print(f"[bold green]Indexed:[/] {count} notes")
```

- [ ] **Add `ytk ingest` command** (after `reindex_cmd`)

```python
@cli.command()
@click.argument("url")
@click.option("--force", is_flag=True, default=False, help="Skip interest-tag filter.")
def ingest(url: str, force: bool):
    """Fetch a web article, enrich with AI, and store in the vault."""
    from .filter import check_post_enrichment
    from .ingest import enrich_web, fetch_web
    from .store import strip_frontmatter, upsert_doc
    from .vault import write_web_note

    cfg = load_config()

    with console.status("[bold cyan]Fetching article...[/]"):
        try:
            content = fetch_web(url)
        except ValueError as exc:
            console.print(f"[red]Fetch failed:[/] {exc}")
            raise SystemExit(1)

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", no_wrap=True)
    info.add_column()
    info.add_row("Title", content.title)
    if content.author:
        info.add_row("Author", content.author)
    if content.date:
        info.add_row("Date", content.date)
    info.add_row("Words", f"{len(content.text.split()):,}")
    console.print(Panel(info, title="[bold]Article[/]", box=box.ROUNDED))

    with console.status("[bold cyan]Enriching with Claude Haiku...[/]"):
        result = enrich_web(content)

    post_result = check_post_enrichment(result, cfg)
    if not _prompt_on_failures(post_result, force):
        raise SystemExit(0)

    console.print(Panel(f"[italic]{result.thesis}[/]", title="[bold]Thesis[/]", box=box.ROUNDED))
    console.print(Panel(result.summary, title="[bold]Summary[/]", box=box.ROUNDED))

    try:
        note_path = write_web_note(content.url, content.title, content.author, content.date, result)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        doc_id = "web_" + note_path.stem[:60].replace(" ", "_")
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(doc_id, body, {
            "doc_id": doc_id,
            "tags": ", ".join(result.interest_tags),
            "source_path": str(note_path),
        })
    except EnvironmentError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")
```

- [ ] **Add `ytk gc` command** (after `ingest`)

```python
@cli.command()
@click.option("--prune", type=int, default=None, metavar="DAYS",
              help="Archive memories older than N days and remove from ChromaDB.")
@click.option("--refresh-projects", is_flag=True, default=False,
              help="Re-run seed for project memories older than 30 days.")
@click.option("--dry-run", is_flag=True, default=False)
def gc(prune: int | None, refresh_projects: bool, dry_run: bool):
    """Manage vault memory lifecycle — list ages, prune stale entries, refresh projects."""
    import subprocess
    from .store import delete_doc
    from .vault import _get_vault_path

    try:
        vault_path = _get_vault_path()
    except EnvironmentError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    mem_dir = vault_path / "inbox" / "memories"
    if not mem_dir.exists() or not list(mem_dir.glob("*.md")):
        console.print("[yellow]No memories found.[/]")
        return

    now = datetime.now()
    notes = sorted(mem_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)

    table = Table("File", "Age", "Tags", box=box.SIMPLE, show_header=True)
    for p in notes:
        age_days = (now - datetime.fromtimestamp(p.stat().st_mtime)).days
        content = p.read_text(encoding="utf-8")
        tag_match = re.search(r"^tags:\s*\n((?:  - .+\n)*)", content, re.MULTILINE)
        tags = ", ".join(re.findall(r"  - (.+)", tag_match.group(1))) if tag_match else ""
        table.add_row(p.name[:55], f"{age_days}d", tags[:45])
    console.print(Panel(table, title=f"[bold]Memories ({len(notes)})[/]", box=box.ROUNDED))

    if prune is not None:
        cutoff = now - timedelta(days=prune)
        to_archive = [p for p in notes if datetime.fromtimestamp(p.stat().st_mtime) < cutoff]
        if not to_archive:
            console.print(f"[green]No memories older than {prune} days.[/]")
        else:
            console.print(f"\n[yellow]{len(to_archive)} memories older than {prune} days.[/]")
            if dry_run:
                for p in to_archive:
                    console.print(f"  [dim]would archive:[/] {p.name}")
            else:
                archive_dir = mem_dir / "archived"
                archive_dir.mkdir(exist_ok=True)
                for p in to_archive:
                    content = p.read_text(encoding="utf-8")
                    id_match = re.search(r"^id:\s*(.+)$", content, re.MULTILINE)
                    if id_match:
                        try:
                            delete_doc(id_match.group(1).strip())
                        except Exception:
                            pass
                    p.rename(archive_dir / p.name)
                    console.print(f"  [dim]archived:[/] {p.name}")
                console.print(f"\n[bold green]Archived {len(to_archive)} memories.[/]")

    if refresh_projects:
        proj_mems = [
            p for p in notes
            if "project-context" in p.read_text(encoding="utf-8")
        ]
        cutoff = now - timedelta(days=30)
        stale = [p for p in proj_mems if datetime.fromtimestamp(p.stat().st_mtime) < cutoff]
        if not stale:
            console.print("[green]All project memories are fresh (< 30 days).[/]")
        else:
            console.print(f"[cyan]Refreshing {len(stale)} stale project memories...[/]")
            if not dry_run:
                seed_script = Path(__file__).parent.parent / "scripts" / "seed_memory.py"
                result = subprocess.run(
                    ["uv", "run", str(seed_script), "--force", "--max-sessions", "5"],
                    cwd=Path(__file__).parent.parent,
                )
                if result.returncode == 0:
                    console.print("[bold green]Project memories refreshed.[/]")
                else:
                    console.print("[red]Seed script failed — check output above.[/]")
```

- [ ] **Verify all commands register**

```bash
uv run ytk --help
```

Expected output includes: `remember`, `reindex`, `ingest`, `gc` alongside existing commands.

- [ ] **Commit**

```bash
git add ytk/cli.py
git commit -m "feat(cli): add ytk remember, reindex, ingest, gc commands"
```

---

### Task 7: seed_memory.py --recent flag + Stop hook

**Files:**
- Modify: `scripts/seed_memory.py`
- Modify: `~/.claude/settings.json`

**Depends on:** Nothing (seed script is standalone; hook just calls it)

- [ ] **Add `--recent` argument to the argparse block in `main()`**

After the existing `--dry-run` argument:

```python
parser.add_argument(
    "--recent",
    action="store_true",
    help="Re-seed only the project whose JSONL was most recently modified (session-end use).",
)
```

- [ ] **Add early-return logic at the top of the project iteration loop in `main()`**

Insert after `projects = [d for d in CLAUDE_DIR.iterdir() if d.is_dir()]` and before the `print(f"Found {len(projects)}...")` line:

```python
    if args.recent:
        import time
        all_jsonls = [
            (jf.stat().st_mtime, proj_dir)
            for proj_dir in projects
            for jf in proj_dir.glob("*.jsonl")
        ]
        if not all_jsonls:
            print("--recent: no JSONL files found.")
            return
        most_recent_mtime, most_recent_proj = max(all_jsonls, key=lambda x: x[0])
        if time.time() - most_recent_mtime > 300:
            print("--recent: last session > 5 minutes ago, skipping.")
            return
        projects = [most_recent_proj]
        args.force = True
        print(f"--recent: reseeding {project_name_from_dir(most_recent_proj.name)}")
```

- [ ] **Verify dry run with --recent works**

```bash
uv run scripts/seed_memory.py --recent --dry-run 2>&1
```

Expected: either "no recent session" or shows the most recent project's turns.

- [ ] **Register Stop hook in ~/.claude/settings.json**

Read `~/.claude/settings.json`. In the `hooks` object, add a `Stop` key alongside the existing `PreToolUse` and `PostToolUse` keys:

```json
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "cd /Users/melocoton/Developer/ytk && uv run scripts/seed_memory.py --recent --max-sessions 1 >> ~/.ytk/seed.log 2>&1"
      }
    ]
  }
]
```

- [ ] **Commit**

```bash
git add scripts/seed_memory.py
git commit -m "feat(seed): add --recent flag for stop-hook auto-reseed"
```

---

### Task 8: Integration — reindex existing vault, smoke test, update roadmap

**Files:**
- Run commands
- Modify: `ytk/CLAUDE.md` (roadmap table)
- Modify: vault `wiki/hot.md`

- [ ] **Run ytk reindex to index existing vault content**

```bash
uv run ytk reindex
```

Expected: `Indexed: N notes` where N > 0 (the 12 seeded memories + any projects/decisions content).

- [ ] **Smoke test ytk remember**

```bash
uv run ytk remember "Phase 5B-5G sprint complete — ytk now has full write path, web ingestion, and auto-reseed on session end" --tags ytk,sprint
```

Expected: `Memory stored: .../inbox/memories/2026-04-16-phase-5b-5g-sprint-complete....md`

- [ ] **Smoke test ytk gc (list only)**

```bash
uv run ytk gc
```

Expected: table of memories with ages, no changes.

- [ ] **Smoke test ytk ingest (optional — requires a real URL)**

```bash
uv run ytk ingest https://trafilatura.readthedocs.io/en/latest/ --force
```

Expected: fetches, enriches, writes to `sources/web/`.

- [ ] **Verify vault_search finds the remember note**

```bash
uv run ytk search "sprint complete write path"
```

Expected: the note from the smoke test appears in results.

- [ ] **Update CLAUDE.md roadmap table**

Change Phase 5 row and add rows for 5B-5G:

```markdown
| 5   | done    | MCP server — expose vault + vector store to Claude sessions |
| 5B  | done    | `ytk remember` CLI — user-side quick capture |
| 5C  | done    | Auto-index vault writes — vault_write + vault_reindex |
| 5D  | done    | Global session-end capture rule in CLAUDE.md |
| 5E  | done    | `ytk ingest <url>` — web article ingestion via trafilatura |
| 5F  | done    | `ytk gc` — memory lifecycle: prune + refresh-projects |
| 5G  | done    | Stop hook — auto-reseed active project after every session |
```

- [ ] **Update wiki/hot.md** with current sprint state (all phases 5-5G done, new commands available)

- [ ] **Final commit**

```bash
git add ytk/CLAUDE.md ytk/cli.py ytk/store.py ytk/vault.py ytk/ingest.py ytk/mcp_server.py scripts/seed_memory.py pyproject.toml uv.lock
git commit -m "feat: complete shared brain sprint (phases 5B-5G)"
```
