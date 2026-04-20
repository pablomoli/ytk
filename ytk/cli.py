"""ytk CLI entry point."""

from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from .config import load_config
from .filter import check_pre_transcript, check_post_enrichment, FilterResult
from .metadata import fetch_metadata
from .transcript import fetch_transcript, segments_to_text
from .enrich import enrich
from .vault import write_note, NoteAlreadyExists
from .store import upsert, search_videos, search_segments

load_dotenv(Path.home() / ".ytk" / ".env")  # global install location
load_dotenv()  # project-local .env for dev use (won't override already-loaded vars)
console = Console()


from contextlib import contextmanager

@contextmanager
def _nullctx():
    yield


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_date(yyyymmdd: str) -> str:
    try:
        return datetime.strptime(yyyymmdd, "%Y%m%d").strftime("%B %d, %Y")
    except Exception:
        return yyyymmdd


def _prompt_on_failures(result: FilterResult, force: bool) -> bool:
    """
    If the filter result has failures, print each one and ask the user whether
    to proceed. Returns True if execution should continue, False to abort.
    With --force, always continues without prompting.
    """
    if result.passed:
        return True
    if force:
        for f in result.failures:
            console.print(f"[yellow]Filter skipped (--force):[/] {f.detail}")
        return True
    for f in result.failures:
        console.print(f"\n[yellow]Filter:[/] {f.detail}")
        if not click.confirm("Add anyway?", default=False):
            return False
    return True


@click.group()
def cli():
    """ytk — personal YouTube knowledge system."""


@cli.command()
@click.argument("url")
@click.option("--force", is_flag=True, default=False, help="Skip all filter prompts.")
def add(url: str, force: bool):
    """Fetch transcript, enrich with AI, and ingest a YouTube video."""
    cfg = load_config()

    with console.status("[bold cyan]Fetching metadata...[/]"):
        meta = fetch_metadata(url)

    # --- pre-transcript filter (duration) ---
    pre_result = check_pre_transcript(meta, cfg)
    if not _prompt_on_failures(pre_result, force):
        raise SystemExit(0)

    with console.status("[bold cyan]Fetching transcript...[/]"):
        try:
            segments, source = fetch_transcript(url, whisper_model=cfg.whisper_model)
        except Exception as exc:
            if cfg.filters.require_captions:
                console.print(f"\n[yellow]Filter:[/] No captions available ({exc})")
                if not force and not click.confirm("Add anyway?", default=False):
                    raise SystemExit(0)
            raise

    # --- metadata panel ---
    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", no_wrap=True)
    info.add_column()
    info.add_row("Title", meta["title"])
    info.add_row("Uploader", meta["uploader"])
    info.add_row("Date", _fmt_date(meta["upload_date"]))
    info.add_row("Duration", _fmt_duration(meta["duration"]))
    if meta["view_count"]:
        info.add_row("Views", f"{meta['view_count']:,}")
    if meta["tags"]:
        info.add_row("Tags", ", ".join(meta["tags"][:8]))
    info.add_row("Transcript via", source)
    console.print(Panel(info, title="[bold]Metadata[/]", box=box.ROUNDED))

    # --- chapters ---
    if meta["chapters"]:
        ch_table = Table("Time", "Chapter", box=box.SIMPLE, show_header=True)
        for ch in meta["chapters"]:
            ch_table.add_row(_fmt_duration(ch["start_time"]), ch["title"])
        console.print(Panel(ch_table, title="[bold]Chapters[/]", box=box.ROUNDED))

    # --- transcript preview ---
    full_text = segments_to_text(segments)
    preview = textwrap.fill(full_text[:800], width=80)
    if len(full_text) > 800:
        preview += f"\n[dim]... ({len(full_text):,} chars total, {len(segments)} segments)[/dim]"

    console.print(
        Panel(
            preview,
            title=f"[bold]Transcript[/] [dim]({len(segments)} segments)[/dim]",
            box=box.ROUNDED,
        )
    )

    # --- visual frame extraction ---
    visual_blocks: list[dict] | None = None
    try:
        from .vision import download_video_temp, extract_frames, hint_detect, image_blocks
        with console.status("[bold cyan]Scanning for visual content...[/]"):
            hint_ts = hint_detect(segments)
        if hint_ts:
            with console.status("[bold cyan]Downloading video for frame extraction...[/]"):
                video_tmp = download_video_temp(url)
            try:
                with console.status("[bold cyan]Extracting frames...[/]"):
                    frame_bytes = extract_frames(video_tmp, hint_ts, baseline_n=4)
                visual_blocks = image_blocks(frame_bytes=frame_bytes) if frame_bytes else None
            finally:
                video_tmp.unlink(missing_ok=True)
    except Exception:
        visual_blocks = None

    # --- AI enrichment ---
    with console.status("[bold cyan]Enriching with Claude Haiku...[/]"):
        result = enrich(full_text, meta, visual_blocks=visual_blocks)

    # --- post-enrichment filter (interest tags) ---
    post_result = check_post_enrichment(result, cfg)
    if not _prompt_on_failures(post_result, force):
        raise SystemExit(0)

    # thesis
    console.print(Panel(f"[italic]{result.thesis}[/]", title="[bold]Thesis[/]", box=box.ROUNDED))

    # summary
    console.print(Panel(result.summary, title="[bold]Commentary[/]", box=box.ROUNDED))

    # key concepts + interest tags side by side
    grid = Table.grid(padding=(0, 4))
    grid.add_column()
    grid.add_column()

    concepts = "\n".join(f"[cyan]•[/] {c}" for c in result.key_concepts)
    tags = " ".join(f"[bold cyan]#{t}[/]" for t in result.interest_tags)
    grid.add_row(concepts, tags)
    console.print(Panel(grid, title="[bold]Key Concepts & Tags[/]", box=box.ROUNDED))

    # insights
    insights = "\n".join(f"[yellow]>[/] {i}" for i in result.insights)
    console.print(Panel(insights, title="[bold]Insights[/]", box=box.ROUNDED))

    # key moments
    if result.key_moments:
        moments_table = Table("Timestamp", "Moment", box=box.SIMPLE, show_header=True)
        for m in result.key_moments:
            moments_table.add_row(f"[cyan]{m.timestamp}[/]", m.description)
        console.print(Panel(moments_table, title="[bold]Key Moments[/]", box=box.ROUNDED))

    # --- write vault note ---
    try:
        note_path = write_note(meta, result, segments)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")
    except EnvironmentError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")

    # --- upsert into vector store ---
    with console.status("[bold cyan]Indexing embeddings...[/]"):
        upsert(meta, result, segments)


@cli.command()
@click.argument("video_id")
@click.argument("query")
@click.option("-n", default=5, show_default=True, help="Number of results.")
def dive(video_id: str, query: str, n: int):
    """Segment-level semantic search within a specific video.

    VIDEO_ID is the YouTube video ID (e.g. dQw4w9WgXcQ).
    """
    with console.status("[bold cyan]Searching segments...[/]"):
        results = search_segments(query, video_id=video_id, n=n)

    if not results:
        console.print(
            f"[yellow]No results for video[/] [bold]{video_id}[/]. "
            "The video may not be ingested yet — run [bold]ytk add <url>[/] first."
        )
        return

    console.print(f"\n[bold]{results[0].title}[/]  [dim]{video_id}[/]\n")

    for i, r in enumerate(results, 1):
        m, s = divmod(int(r.start), 60)
        timestamp = f"{m}:{s:02d}"
        match_pct = f"{(1 - r.distance):.0%}"
        preview = textwrap.fill(r.text[:300], width=72)
        if len(r.text) > 300:
            preview += "..."

        console.print(Panel(
            f"{preview}\n\n"
            f"[bold cyan]Timestamp[/]  [link={r.timestamp_url}]{timestamp}[/link]  "
            f"[bold cyan]Match[/] {match_pct}  "
            f"[bold cyan]URL[/] {r.timestamp_url}",
            title=f"[bold]{i}. @ {timestamp}[/]",
            box=box.ROUNDED,
        ))


@cli.command()
def auth():
    """Authenticate with YouTube Data API v3 (one-time OAuth flow)."""
    from urllib.parse import urlparse, parse_qs
    from .scheduler import _CLIENT_SECRETS, _SCOPES, _TOKEN_FILE
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not _CLIENT_SECRETS.exists():
        console.print(f"[red]Missing:[/] {_CLIENT_SECRETS}")
        raise SystemExit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(_CLIENT_SECRETS), _SCOPES)
    flow.redirect_uri = "http://localhost"
    auth_url, _ = flow.authorization_url(prompt="consent")

    console.print(f"\n[bold]1. Open this URL in your browser:[/]\n\n{auth_url}\n")
    console.print("[bold]2.[/] Click through the warning → authorize the app.")
    console.print("[bold]3.[/] Your browser will land on a page that fails to load (localhost).")
    console.print("[bold]4.[/] Copy the full URL from your address bar and paste it here.\n")

    redirect_url = input("Paste the redirect URL: ").strip()

    params = parse_qs(urlparse(redirect_url).query)
    if "error" in params:
        console.print(f"[red]Auth failed:[/] {params['error']}")
        raise SystemExit(1)

    code = (params.get("code") or [None])[0]
    if not code:
        console.print("[red]No code found in URL.[/]")
        raise SystemExit(1)

    flow.fetch_token(code=code)
    _TOKEN_FILE.write_text(flow.credentials.to_json(), encoding="utf-8")
    console.print(f"\n[bold green]Authenticated.[/] Token saved to {_TOKEN_FILE}")


@cli.command()
@click.option("--dry-run", is_flag=True, default=False, help="Print what would be synced without running the pipeline.")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Print step-by-step progress for each video.")
def sync(dry_run: bool, verbose: bool):
    """Poll the 'ytk' YouTube playlist and ingest new videos."""
    from .scheduler import authenticate, sync as _sync
    cfg = load_config()

    with console.status("[bold cyan]Authenticating...[/]"):
        service = authenticate()

    verb = "dry-run" if dry_run else "syncing"
    status_cm = console.status(f"[bold cyan]{verb.capitalize()} ytk playlist...[/]") if not verbose else _nullctx()
    with status_cm:
        result = _sync(service, cfg, dry_run=dry_run, verbose=verbose)

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold cyan", no_wrap=True)
    summary.add_column()
    summary.add_row("Seen", str(result.seen))
    summary.add_row("Already processed", str(result.already_processed))
    summary.add_row("New", str(result.new))
    summary.add_row("Ingested", str(result.ingested))
    summary.add_row("Skipped", str(result.skipped))
    summary.add_row("Failed", str(result.failed))
    console.print(Panel(summary, title="[bold]Sync Result[/]", box=box.ROUNDED))


@cli.command()
@click.argument("query")
@click.option("-n", default=5, show_default=True, help="Number of results.")
def search(query: str, n: int):
    """Semantic search across ingested videos."""
    with console.status("[bold cyan]Searching...[/]"):
        results = search_videos(query, n=n)

    if not results:
        console.print("[yellow]No results.[/] Run [bold]ytk sync[/] to ingest videos first.")
        return

    for i, r in enumerate(results, 1):
        tags = " ".join(f"[bold cyan]#{t}[/]" for t in r.tags[:5])
        thesis_line = f"[italic]{r.thesis}[/]" if r.thesis else ""
        summary_preview = textwrap.fill(r.summary[:220], width=72)
        if len(r.summary) > 220:
            summary_preview += "..."

        meta_line = (
            f"[bold cyan]URL[/]  {r.url}\n"
            f"[bold cyan]By[/]   {r.uploader}    "
            f"[bold cyan]Match[/] {(1 - r.distance):.0%}\n"
            f"[bold cyan]Tags[/] {tags or '[dim]none[/]'}"
        )

        body = f"{thesis_line}\n\n{summary_preview}\n\n{meta_line}" if thesis_line else f"{summary_preview}\n\n{meta_line}"
        console.print(Panel(
            body,
            title=f"[bold]{i}. {r.title}[/]",
            box=box.ROUNDED,
        ))


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


@cli.command(name="reindex")
@click.option("--force", is_flag=True, default=False, help="Re-embed all files, ignoring cache.")
def reindex_cmd(force: bool):
    """Index all vault notes into ChromaDB for semantic search."""
    from .vault import _get_brain_path, reindex_vault

    try:
        _get_brain_path()
    except EnvironmentError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    label = "Re-indexing all vault notes..." if force else "Indexing changed vault notes..."
    with console.status(f"[bold cyan]{label}[/]"):
        count = reindex_vault(force=force)

    console.print(f"[bold green]Indexed:[/] {count} notes")


@cli.command(name="graph")
@click.option("--open", "open_browser", is_flag=True, default=False, help="Open graph.html in browser after building.")
@click.option("--output", default=None, help="Output path for graph.html (default: ~/.ytk/graph.html).")
@click.option("--threshold", default=0.75, show_default=True, type=float, help="Semantic similarity cutoff for edges.")
def graph_cmd(open_browser: bool, output: str | None, threshold: float):
    """Build a knowledge graph from all vault notes and export as interactive HTML."""
    import webbrowser
    from .graph import build_graph, export_html, export_json, detect_communities

    default_html = Path.home() / ".ytk" / "graph.html"
    default_json = Path.home() / ".ytk" / "graph.json"
    html_path = Path(output) if output else default_html

    with console.status("[bold cyan]Building graph...[/]"):
        G = build_graph(threshold=threshold)

    if len(G.nodes) == 0:
        console.print("[yellow]No indexed notes found.[/] Run [bold]ytk reindex[/] first.")
        return

    with console.status("[bold cyan]Exporting...[/]"):
        export_html(G, html_path)
        export_json(G, default_json)

    n_communities = len(set(detect_communities(G).values()))
    console.print(f"[bold green]Graph built:[/] {len(G.nodes)} nodes, {len(G.edges)} edges, {n_communities} communities")
    console.print(f"  HTML: {html_path}")
    console.print(f"  JSON: {default_json}")

    if open_browser:
        webbrowser.open(f"file://{html_path.resolve()}")


@cli.command()
@click.argument("url")
@click.option("--force", is_flag=True, default=False, help="Skip interest-tag filter.")
def ingest(url: str, force: bool):
    """Fetch a web article, enrich with AI, and store in the vault."""
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
        doc_id = "web_" + re.sub(r"[^a-zA-Z0-9_-]", "_", note_path.stem[:60])
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(doc_id, body, {
            "doc_id": doc_id,
            "tags": ", ".join(result.interest_tags),
            "source_path": str(note_path),
        })
    except EnvironmentError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")


@cli.command(name="add-instagram")
@click.argument("url")
def add_instagram(url: str):
    """Fetch an Instagram post, analyze visually with AI, and store in the vault."""
    from .instagram import fetch_instagram
    from .vision import extract_frames, image_blocks
    from .enrich import enrich
    from .vault import write_instagram_note, NoteAlreadyExists
    from .store import strip_frontmatter, upsert_doc

    with console.status("[bold cyan]Fetching Instagram post...[/]"):
        try:
            post = fetch_instagram(url)
        except ValueError as exc:
            console.print(f"[red]Fetch failed:[/] {exc}")
            raise SystemExit(1)

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", no_wrap=True)
    info.add_column()
    info.add_row("Username", f"@{post.username}")
    info.add_row("Date", post.timestamp)
    if post.images:
        info.add_row("Images", str(len(post.images)))
    if post.video_path:
        info.add_row("Reel", "yes")
    if post.caption:
        info.add_row("Caption", post.caption[:120])
    console.print(Panel(info, title="[bold]Instagram Post[/]", box=box.ROUNDED))

    with console.status("[bold cyan]Preparing visual content...[/]"):
        blocks = image_blocks(urls=post.images if post.images else None)
        try:
            if post.video_path:
                frame_bytes = extract_frames(post.video_path, timestamps=[], baseline_n=4)
                blocks += image_blocks(frame_bytes=frame_bytes)
        finally:
            if post.video_path:
                post.video_path.unlink(missing_ok=True)

    meta = {
        "title": f"Instagram post by @{post.username} ({post.timestamp})",
        "uploader": post.username,
        "duration": 0,
        "tags": [],
    }

    with console.status("[bold cyan]Enriching with Claude Haiku...[/]"):
        try:
            result = enrich(post.caption, meta, visual_blocks=blocks if blocks else None)
        except Exception as exc:
            console.print(f"[red]Enrichment failed:[/] {exc}")
            raise SystemExit(1)

    console.print(Panel(f"[italic]{result.thesis}[/]", title="[bold]Thesis[/]", box=box.ROUNDED))
    console.print(Panel(result.summary, title="[bold]Summary[/]", box=box.ROUNDED))

    grid = Table.grid(padding=(0, 4))
    grid.add_column()
    grid.add_column()
    concepts = "\n".join(f"[cyan]•[/] {c}" for c in result.key_concepts)
    tags = " ".join(f"[bold cyan]#{t}[/]" for t in result.interest_tags)
    grid.add_row(concepts, tags)
    console.print(Panel(grid, title="[bold]Key Concepts & Tags[/]", box=box.ROUNDED))

    insights = "\n".join(f"[yellow]>[/] {i}" for i in result.insights)
    console.print(Panel(insights, title="[bold]Insights[/]", box=box.ROUNDED))

    try:
        note_path = write_instagram_note(post, result)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        doc_id = "instagram_" + re.sub(r"[^a-zA-Z0-9_-]", "_", note_path.stem[:60])
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(doc_id, body, {
            "doc_id": doc_id,
            "tags": ", ".join(result.interest_tags),
            "source_path": str(note_path),
        })
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")
    except EnvironmentError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")


def _parse_date(value: str) -> str:
    """Convert natural date shorthands to YYYY-MM-DD. Passes through ISO dates unchanged."""
    from datetime import date, timedelta
    v = value.strip().lower()
    if v == "today":
        return date.today().isoformat()
    if v == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    # "N days ago"
    m = re.match(r"^(\d+)\s+days?\s+ago$", v)
    if m:
        return (date.today() - timedelta(days=int(m.group(1)))).isoformat()
    return value  # assume already YYYY-MM-DD


@cli.command(name="add-imessage")
@click.argument("contact", default="", required=False)
@click.option("--since", default=None, metavar="DATE", help="Start date: YYYY-MM-DD, 'today', 'yesterday', or 'N days ago'.")
@click.option("--until", default=None, metavar="DATE", help="End date: YYYY-MM-DD, 'today', 'yesterday', or 'N days ago'.")
def add_imessage(contact: str, since: str | None, until: str | None):
    """Export an iMessage conversation and ingest it as a journal note.

    CONTACT defaults to $IMESSAGE_SELF. Pass a phone number, Apple ID, or
    contact name to ingest any conversation.
    """
    import shutil
    contact = contact or os.environ.get("IMESSAGE_SELF", "")
    if not contact:
        console.print("[red]No contact specified and IMESSAGE_SELF is not set in ~/.ytk/.env[/]")
        raise SystemExit(1)
    if since:
        since = _parse_date(since)
    if until:
        until = _parse_date(until)
    from .imessage import export_conversation, find_exported_file, parse_txt, enrich_journal
    from .vault import write_journal_note, NoteAlreadyExists
    from .store import strip_frontmatter, upsert_doc

    with console.status("[bold cyan]Exporting conversation...[/]"):
        try:
            export_dir = export_conversation(contact, start_date=since, end_date=until)
        except ValueError as exc:
            console.print(f"[red]Export failed:[/] {exc}")
            raise SystemExit(1)

    try:
        txt_path = find_exported_file(export_dir, contact)
    except ValueError as exc:
        shutil.rmtree(export_dir, ignore_errors=True)
        console.print(f"[red]{exc}[/]")
        raise SystemExit(1)

    thread = parse_txt(txt_path)
    shutil.rmtree(export_dir, ignore_errors=True)

    if not thread.messages:
        console.print("[yellow]No messages found in export.[/]")
        raise SystemExit(0)

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", no_wrap=True)
    info.add_column()
    info.add_row("Contact", thread.contact)
    info.add_row("Date", thread.date)
    info.add_row("Messages", str(len(thread.messages)))
    console.print(Panel(info, title="[bold]iMessage Thread[/]", box=box.ROUNDED))

    with console.status("[bold cyan]Enriching with Claude Haiku...[/]"):
        try:
            result = enrich_journal(thread)
        except Exception as exc:
            console.print(f"[red]Enrichment failed:[/] {exc}")
            raise SystemExit(1)

    console.print(Panel(f"[italic]{result.thesis}[/]", title="[bold]Thesis[/]", box=box.ROUNDED))
    console.print(Panel(result.summary, title="[bold]Summary[/]", box=box.ROUNDED))

    grid = Table.grid(padding=(0, 4))
    grid.add_column()
    grid.add_column()
    concepts = "\n".join(f"[cyan]•[/] {c}" for c in result.key_concepts)
    tags = " ".join(f"[bold cyan]#{t}[/]" for t in result.interest_tags)
    grid.add_row(concepts, tags)
    console.print(Panel(grid, title="[bold]Key Concepts & Tags[/]", box=box.ROUNDED))

    insights = "\n".join(f"[yellow]>[/] {i}" for i in result.insights)
    console.print(Panel(insights, title="[bold]Insights[/]", box=box.ROUNDED))

    try:
        note_path = write_journal_note(thread, result)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        doc_id = "journal_" + re.sub(r"[^a-zA-Z0-9_-]", "_", note_path.stem[:60])
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(doc_id, body, {
            "doc_id": doc_id,
            "tags": ", ".join(result.interest_tags),
            "source_path": str(note_path),
        })
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")
    except EnvironmentError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")


_PRIORITY_COLOR = {"high": "red", "medium": "yellow", "low": "green"}
_ROUTE_LABEL = {"gh-issue": "GH issue", "idea": "inbox/ideas", "investigate": "review"}
_ROUTE_DEFAULT = {"gh-issue": "1", "idea": "2", "investigate": "3"}


def _triage_create_gh(item, cfg, console) -> str | None:
    """Create a GH issue for item. Returns issue URL or None on failure."""
    repo = (
        item.suggested_repo
        if item.suggested_repo and item.suggested_repo in cfg.github_repos
        else (cfg.github_repos[0] if cfg.github_repos else None)
    )
    if not repo:
        return None
    result = subprocess.run(
        ["gh", "issue", "create", "--title", item.title, "--body", item.description, "--repo", repo],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return f"{repo} → {result.stdout.strip()}"
    return None


@cli.command(name="triage")
@click.argument("note_path", default="", required=False)
@click.option("--interactive", "-i", is_flag=True, help="Review and route each item manually.")
def triage(note_path: str, interactive: bool):
    """Extract action items from a vault note and auto-route them.

    NOTE_PATH is relative to the vault root. Defaults to the most recently
    modified note under vault/sources/. Use --interactive to review each item.
    """
    from .triage import extract_action_items

    vault_raw = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if not vault_raw:
        console.print("[red]OBSIDIAN_VAULT_PATH not configured.[/]")
        raise SystemExit(1)
    vault = Path(vault_raw).expanduser()

    if note_path:
        target = Path(note_path) if Path(note_path).is_absolute() else vault / note_path
    else:
        candidates = list((vault / "second-brain" / "sources").rglob("*.md"))
        if not candidates:
            console.print("[red]No notes found in vault/second-brain/sources/.[/]")
            raise SystemExit(1)
        target = max(candidates, key=lambda p: p.stat().st_mtime)

    if not target.exists():
        console.print(f"[red]Note not found:[/] {target}")
        raise SystemExit(1)

    note_text = target.read_text(encoding="utf-8")
    console.print(f"\n[bold]Triaging:[/] {target.name}\n")

    cfg = load_config()

    with console.status("[bold cyan]Extracting action items...[/]"):
        items = extract_action_items(note_text, repos=cfg.github_repos or None)

    if not items:
        console.print("[yellow]No actionable items found.[/]")
        return

    summary = Table("", "Title", "Priority", "Route", box=box.SIMPLE, show_header=True)
    for i, item in enumerate(items, 1):
        pc = _PRIORITY_COLOR[item.priority]
        repo_hint = f" ({item.suggested_repo})" if item.suggested_repo else ""
        summary.add_row(
            str(i), item.title, f"[{pc}]{item.priority}[/]",
            _ROUTE_LABEL[item.suggested_route] + repo_hint,
        )
    console.print(Panel(summary, title=f"[bold]{len(items)} Action Items[/]", box=box.ROUNDED))

    inbox = vault / "second-brain" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    ideas_path = inbox / "ideas.md"
    review_path = inbox / "review.md"
    routed: dict[str, int] = {"gh": 0, "ideas": 0, "review": 0, "skip": 0}

    if not interactive:
        for item in items:
            if item.suggested_route == "gh-issue":
                url = _triage_create_gh(item, cfg, console)
                if url:
                    console.print(f"  [green]GH:[/] {item.title}  [dim]{url}[/]")
                    routed["gh"] += 1
                else:
                    console.print(f"  [yellow]GH skipped (no repo):[/] {item.title}")
                    routed["skip"] += 1
            elif item.suggested_route == "idea":
                entry = f"\n- [ ] {item.title}\n  {item.description}\n"
                with ideas_path.open("a", encoding="utf-8") as f:
                    f.write(entry)
                console.print(f"  [cyan]Idea:[/] {item.title}")
                routed["ideas"] += 1
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
                entry = f"\n- [ ] {item.title} — *{target.stem}* ({date_str})\n  {item.description}\n"
                with review_path.open("a", encoding="utf-8") as f:
                    f.write(entry)
                console.print(f"  [magenta]Review:[/] {item.title}")
                routed["review"] += 1
    else:
        for i, item in enumerate(items, 1):
            pc = _PRIORITY_COLOR[item.priority]
            rl = _ROUTE_LABEL[item.suggested_route]
            default_choice = _ROUTE_DEFAULT[item.suggested_route]

            console.print(Panel(
                f"[bold]{item.title}[/]\n\n{item.description}\n\n"
                f"Priority: [{pc}]{item.priority}[/]  Suggested: [cyan]{rl}[/]",
                title=f"[bold]{i}/{len(items)}[/]",
                box=box.ROUNDED,
            ))
            console.print("  [1] GH issue  [2] Inbox/ideas  [3] Review  [4] Skip")

            while True:
                choice = click.prompt(
                    "  Route", default=default_choice,
                    type=click.Choice(["1", "2", "3", "4"]), show_choices=False,
                )

                if choice == "1":
                    if not cfg.github_repos:
                        console.print("  [yellow]No repos configured. Add github_repos to ~/.ytk/config.yaml[/]")
                        continue
                    if item.suggested_repo and item.suggested_repo in cfg.github_repos:
                        repo = item.suggested_repo
                        console.print(f"  [cyan]Auto-selected:[/] {repo}")
                    else:
                        for j, repo_opt in enumerate(cfg.github_repos, 1):
                            console.print(f"    [{j}] {repo_opt}")
                        repo_idx = click.prompt(
                            "  Repo", type=click.IntRange(1, len(cfg.github_repos)), default=1,
                        ) - 1
                        repo = cfg.github_repos[repo_idx]
                    gh_result = subprocess.run(
                        ["gh", "issue", "create", "--title", item.title, "--body", item.description, "--repo", repo],
                        capture_output=True, text=True,
                    )
                    if gh_result.returncode == 0:
                        console.print(f"  [green]Issue created:[/] {gh_result.stdout.strip()}")
                        routed["gh"] += 1
                        break
                    else:
                        console.print(f"  [red]gh failed:[/] {gh_result.stderr.strip()}")
                        continue

                elif choice == "2":
                    due = click.prompt("  Due date (YYYY-MM-DD or blank)", default="")
                    entry = f"\n- [ ] {item.title}"
                    if due:
                        entry += f" (due: {due})"
                    entry += f"\n  {item.description}\n"
                    with ideas_path.open("a", encoding="utf-8") as f:
                        f.write(entry)
                    console.print("  [green]Added to inbox/ideas.md[/]")
                    routed["ideas"] += 1
                    break

                elif choice == "3":
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    entry = f"\n- [ ] {item.title} — *{target.stem}* ({date_str})\n  {item.description}\n"
                    with review_path.open("a", encoding="utf-8") as f:
                        f.write(entry)
                    console.print("  [green]Added to inbox/review.md[/]")
                    routed["review"] += 1
                    break

                else:
                    routed["skip"] += 1
                    break

            console.print()

    parts = []
    if routed["gh"]:
        parts.append(f"{routed['gh']} GH issue(s)")
    if routed["ideas"]:
        parts.append(f"{routed['ideas']} idea(s)")
    if routed["review"]:
        parts.append(f"{routed['review']} review item(s)")
    if routed["skip"]:
        parts.append(f"{routed['skip']} skipped")
    console.print(f"\n[bold green]Done:[/] {', '.join(parts) or 'nothing routed'}")


@cli.command(name="review")
def review():
    """Print pending investigate items from inbox/review.md."""
    vault_raw = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if not vault_raw:
        console.print("[red]OBSIDIAN_VAULT_PATH not configured.[/]")
        raise SystemExit(1)
    vault = Path(vault_raw).expanduser()
    review_path = vault / "second-brain" / "inbox" / "review.md"

    if not review_path.exists():
        console.print("[yellow]No review items yet. Run ytk triage to add some.[/]")
        return

    lines = review_path.read_text(encoding="utf-8").splitlines()

    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        if line.startswith("- [ ] "):
            if current:
                items.append(current)
            current = {"header": line[6:], "desc": ""}
        elif line.startswith("- [x] "):
            if current:
                items.append(current)
            current = None
        elif current is not None and line.startswith("  ") and line.strip():
            current["desc"] = line.strip()
    if current:
        items.append(current)

    if not items:
        console.print("[yellow]No pending review items.[/]")
        return

    t = Table(box=box.SIMPLE, show_header=True)
    t.add_column("Item", no_wrap=False, max_width=50)
    t.add_column("Description", no_wrap=False)
    for item in items:
        t.add_row(item["header"], item["desc"])
    console.print(Panel(t, title=f"[bold]Review Items ({len(items)} pending)[/]", box=box.ROUNDED))


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
    from .vault import _get_brain_path

    try:
        vault_path = _get_brain_path()
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
            if dry_run:
                for p in stale:
                    console.print(f"  [dim]would refresh:[/] {p.name}")
            else:
                seed_script = Path(__file__).parent.parent / "scripts" / "seed_memory.py"
                result = subprocess.run(
                    ["uv", "run", str(seed_script), "--force", "--max-sessions", "5"],
                    cwd=Path(__file__).parent.parent,
                )
                if result.returncode == 0:
                    console.print("[bold green]Project memories refreshed.[/]")
                else:
                    console.print("[red]Seed script failed — check output above.[/]")


@cli.command(name="index")
def index_cmd():
    """Rebuild wiki/index.md by scanning the vault from scratch."""
    from .vault import rebuild_index, _get_brain_path

    try:
        vault_path = _get_brain_path()
    except EnvironmentError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    with console.status("[bold cyan]Rebuilding index...[/]"):
        rebuild_index()

    console.print(f"[bold green]Index rebuilt:[/] {vault_path / 'wiki' / 'index.md'}")


@cli.command()
def dashboard():
    """Generate today's inbox/review-YYYY-MM-DD.md vault snapshot."""
    from .vault import _get_brain_path, write_raw

    try:
        vault_path = _get_brain_path()
    except EnvironmentError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    cutoff = today - timedelta(days=7)

    sections: list[str] = [f"# Daily Review — {today_str}\n"]

    # Recent memories (last 7 days)
    mem_dir = vault_path / "inbox" / "memories"
    if mem_dir.exists():
        recent = [
            p for p in sorted(mem_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if datetime.fromtimestamp(p.stat().st_mtime) >= cutoff
        ]
        if recent:
            rows = "\n".join(f"- [[second-brain/inbox/memories/{p.stem}]]" for p in recent)
            sections.append(f"## Recent Memories (last 7 days)\n{rows}\n")

    # Recent videos
    youtube_dir = vault_path / "sources" / "youtube"
    if youtube_dir.exists():
        recent_videos = sorted(youtube_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        if recent_videos:
            rows = "\n".join(f"- [[second-brain/sources/youtube/{p.stem}]]" for p in recent_videos)
            sections.append(f"## Recent Videos\n{rows}\n")

    # Active projects
    projects_dir = vault_path / "projects"
    if projects_dir.exists():
        proj_rows: list[str] = []
        for proj in sorted(projects_dir.iterdir()):
            if proj.is_dir():
                briefs = sorted(proj.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
                if briefs:
                    proj_rows.append(f"- **{proj.name}** — [[second-brain/projects/{proj.name}/{briefs[0].stem}]]")
        if proj_rows:
            sections.append("## Active Projects\n" + "\n".join(proj_rows) + "\n")

    # Inbox items (not dated review files)
    inbox_dir = vault_path / "inbox"
    if inbox_dir.exists():
        inbox_items = [
            p for p in sorted(inbox_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not p.stem.startswith("review-")
        ]
        if inbox_items:
            rows = "\n".join(f"- [[second-brain/inbox/{p.stem}]]" for p in inbox_items)
            sections.append(f"## Inbox\n{rows}\n")

    content = "\n".join(sections)
    rel_path = f"second-brain/inbox/review-{today_str}.md"
    with console.status("[bold cyan]Writing dashboard...[/]"):
        note_path = write_raw(rel_path, content)

    console.print(f"[bold green]Dashboard written:[/] {note_path}")


@cli.group()
def schedule():
    """Manage the nightly ytk launchd scheduler."""


@schedule.command(name="install")
@click.option("--hour", default=6, show_default=True, help="Hour (0-23) to run the job.")
def schedule_install(hour: int):
    """Install a launchd job to run ytk index + dashboard nightly."""
    ytk_bin = shutil.which("ytk")
    if not ytk_bin:
        console.print("[red]ytk binary not found in PATH.[/] Run [bold]uv tool install .[/] first.")
        raise SystemExit(1)

    log_path = Path.home() / ".ytk" / "nightly.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    plist_label = "com.ytk.nightly"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{plist_label}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{plist_label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>-c</string>
        <string>{ytk_bin} sync &amp;&amp; {ytk_bin} index &amp;&amp; {ytk_bin} dashboard</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""
    plist_path.write_text(plist_content, encoding="utf-8")

    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    console.print(f"[bold green]Installed:[/] {plist_path}")
    console.print(f"Runs at [bold]{hour:02d}:00[/] daily. Logs: {log_path}")


@schedule.command(name="uninstall")
def schedule_uninstall():
    """Remove the nightly launchd job."""
    plist_label = "com.ytk.nightly"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{plist_label}.plist"

    if not plist_path.exists():
        console.print("[yellow]No plist found.[/] Nothing to uninstall.")
        return

    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    plist_path.unlink()
    console.print(f"[bold green]Uninstalled:[/] {plist_path}")
