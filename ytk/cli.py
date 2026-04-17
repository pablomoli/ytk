"""ytk CLI entry point."""

from __future__ import annotations

import os
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

load_dotenv()
console = Console()


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
            segments, source = fetch_transcript(url)
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

    # --- AI enrichment ---
    with console.status("[bold cyan]Enriching with Claude Haiku...[/]"):
        result = enrich(full_text, meta)

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
def sync(dry_run: bool):
    """Poll the 'ytk' YouTube playlist and ingest new videos."""
    from .scheduler import authenticate, sync as _sync
    cfg = load_config()

    with console.status("[bold cyan]Authenticating...[/]"):
        service = authenticate()

    verb = "dry-run" if dry_run else "syncing"
    with console.status(f"[bold cyan]{verb.capitalize()} ytk playlist...[/]"):
        result = _sync(service, cfg, dry_run=dry_run)

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


@cli.command(name="index")
def index_cmd():
    """Rebuild wiki/index.md by scanning the vault from scratch."""
    from .vault import rebuild_index, _get_vault_path

    try:
        vault_path = _get_vault_path()
    except EnvironmentError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    with console.status("[bold cyan]Rebuilding index...[/]"):
        rebuild_index()

    console.print(f"[bold green]Index rebuilt:[/] {vault_path / 'wiki' / 'index.md'}")


@cli.command()
def dashboard():
    """Generate today's inbox/review-YYYY-MM-DD.md vault snapshot."""
    from .vault import _get_vault_path, write_raw

    try:
        vault_path = _get_vault_path()
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
            rows = "\n".join(f"- [[inbox/memories/{p.stem}]]" for p in recent)
            sections.append(f"## Recent Memories (last 7 days)\n{rows}\n")

    # Recent videos
    youtube_dir = vault_path / "sources" / "youtube"
    if youtube_dir.exists():
        recent_videos = sorted(youtube_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        if recent_videos:
            rows = "\n".join(f"- [[sources/youtube/{p.stem}]]" for p in recent_videos)
            sections.append(f"## Recent Videos\n{rows}\n")

    # Active projects
    projects_dir = vault_path / "projects"
    if projects_dir.exists():
        proj_rows: list[str] = []
        for proj in sorted(projects_dir.iterdir()):
            if proj.is_dir():
                briefs = sorted(proj.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
                if briefs:
                    proj_rows.append(f"- **{proj.name}** — [[projects/{proj.name}/{briefs[0].stem}]]")
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
            rows = "\n".join(f"- [[inbox/{p.stem}]]" for p in inbox_items)
            sections.append(f"## Inbox\n{rows}\n")

    content = "\n".join(sections)
    rel_path = f"inbox/review-{today_str}.md"
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
        <string>{ytk_bin} index &amp;&amp; {ytk_bin} dashboard</string>
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
