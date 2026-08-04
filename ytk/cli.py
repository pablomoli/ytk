# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""ytk CLI entry point."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timedelta
from pathlib import Path

import click
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_config
from .enrich import enrich
from .filter import FilterResult, check_post_enrichment, check_pre_transcript
from .memo import (
    AUDIO_DIR,
)
from .memo import (
    execute_route as memo_execute,
)
from .memo import (
    finalize_memo_note as memo_finalize,
)
from .memo import (
    index_memo_note as memo_index,
)
from .memo import (
    notify as memo_notify,
)
from .memo import (
    record as memo_record,
)
from .memo import (
    route as memo_route,
)
from .memo import (
    transcribe as memo_transcribe,
)
from .memo import (
    write_memo_note as memo_write_note,
)
from .transcript import fetch_transcript, segments_to_text
from .vault import LINK_REMINDER, NoteAlreadyExists, write_note
from .workboard_cli import work as work_command

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


def _collect_feed_urls(file: str | None, urls: tuple[str, ...]) -> list[str]:
    """Merge URLs from args and an optional file (one per line, # comments skipped),
    preserving first-seen order and dropping duplicates."""
    collected: list[str] = list(urls)
    if file:
        for line in Path(file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                collected.append(line)
    seen: set[str] = set()
    out: list[str] = []
    for u in collected:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


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


cli.add_command(work_command)


@cli.command()
@click.argument("url")
@click.option("--force", is_flag=True, default=False, help="Skip all filter prompts.")
@click.option("--note", default="", help="Your thought about this save; steers enrichment.")
@click.pass_context
def add(ctx: click.Context, url: str, force: bool, note: str):
    """Fetch and ingest a URL, dispatched by source."""
    from .metadata import fetch_metadata  # deferred: yt_dlp costs ~75ms (#146)
    from .store import upsert  # deferred: chromadb costs ~330ms (#146)

    if re.search(r"instagram\.com/", url):
        ctx.invoke(add_instagram, url=url, note=note)
        return
    if re.search(r"tiktok\.com/", url):
        ctx.invoke(add_tiktok, url=url, note=note)
        return
    if re.search(r"pinterest\.com/", url):
        ctx.invoke(add_pinterest, url=url, note=note)
        return
    if re.search(r"reddit\.com/r/", url):
        ctx.invoke(add_reddit, url=url, note=note)
        return
    if not re.search(r"(?:youtube\.com/|youtu\.be/)", url):
        ctx.invoke(ingest, url=url, force=force, note=note)
        return

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
    frame_bytes: list[bytes] = []
    try:
        from .vision import download_video_temp, extract_frames, hint_detect, image_blocks

        with console.status("[bold cyan]Scanning for visual content...[/]"):
            hint_ts = hint_detect(segments)
        if hint_ts:
            with console.status("[bold cyan]Downloading video for frame extraction...[/]"):
                video_tmp = download_video_temp(url)
            try:
                with console.status("[bold cyan]Extracting frames...[/]"):
                    frame_bytes = extract_frames(video_tmp, hint_ts, baseline_n=4) or []
                MAX_FRAMES = 8
                if len(frame_bytes) > MAX_FRAMES:
                    frame_bytes = frame_bytes[:MAX_FRAMES]
                visual_blocks = image_blocks(frame_bytes=frame_bytes) if frame_bytes else None
            finally:
                video_tmp.unlink(missing_ok=True)
    except Exception:
        visual_blocks = None

    # --- AI enrichment ---
    with console.status("[bold cyan]Enriching via Claude Code...[/]"):
        result = enrich(full_text, meta, visual_blocks=visual_blocks, user_note=note)

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
        note_path = write_note(meta, result, segments, frame_bytes=frame_bytes or None)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        console.print(LINK_REMINDER, style="dim", markup=False)
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")
    except OSError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")

    # --- upsert into vector store ---
    with console.status("[bold cyan]Indexing embeddings...[/]"):
        upsert(meta, result, segments)


@cli.command(name="feed")
@click.argument("urls", nargs=-1)
@click.option(
    "--file",
    "-f",
    "file",
    type=click.Path(exists=True),
    default=None,
    help="Text file of URLs, one per line (# comments allowed).",
)
@click.option("--force", is_flag=True, default=False, help="Skip all filter prompts.")
@click.pass_context
def feed(ctx: click.Context, urls: tuple[str, ...], file: str | None, force: bool):
    """Batch-ingest a list of URLs (reels, TikToks, videos, articles)."""
    items = _collect_feed_urls(file, urls)
    if not items:
        console.print("[yellow]No URLs provided.[/] Pass URLs or --file <path>.")
        return

    from ytk import capture_log
    from ytk.reels import classify_url

    ok = 0
    skipped = 0
    failed = 0
    for i, url in enumerate(items, 1):
        console.rule(f"[bold]{i}/{len(items)}[/] {url}")
        attempt_started = time.time()
        try:
            ctx.invoke(add, url=url, force=force)
            ok += 1
            outcome, error = "ok", None
        except SystemExit as exc:
            if exc.code in (0, None):
                skipped += 1
                console.print("[dim]skipped (filtered or already ingested)[/]")
                outcome, error = "skipped", None
            else:
                failed += 1
                console.print(f"[red]failed:[/] exited {exc.code}")
                outcome, error = "error", f"exited {exc.code}"
        except Exception as exc:
            failed += 1
            console.print(f"[red]failed:[/] {exc}")
            outcome, error = "error", str(exc)
        capture_log.log_capture(
            "feed",
            url,
            source=classify_url(url),
            outcome=outcome,
            error=error,
            duration_s=time.time() - attempt_started,
        )

    table = Table(box=box.SIMPLE, title="Feed Result")
    table.add_column("Total", justify="right")
    table.add_column("OK", justify="right", style="green")
    table.add_column("Skipped", justify="right", style="yellow")
    table.add_column("Failed", justify="right", style="red")
    table.add_row(str(len(items)), str(ok), str(skipped), str(failed))
    console.print(table)


@cli.command(name="reels")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="List pending links without ingesting or saving anything.",
)
@click.option(
    "--all",
    "ingest_all",
    is_flag=True,
    default=False,
    help="Ingest every pending link without the interactive picker.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Cap how many links get ingested; the rest stay pending.",
)
@click.option(
    "--gallery",
    is_flag=True,
    default=False,
    help="Open a browser gallery of cover images before picking.",
)
@click.option(
    "--rebuild",
    is_flag=True,
    default=False,
    help="Re-read the whole thread to rebuild pending with metadata.",
)
@click.pass_context
def reels(
    ctx: click.Context,
    dry_run: bool,
    ingest_all: bool,
    limit: int | None,
    gallery: bool,
    rebuild: bool,
):
    """Sync reels from your Instagram DM capture thread — pick which to ingest."""
    from . import reels as reels_mod

    sessionid = os.environ.get("INSTAGRAM_SESSIONID", "")
    try:
        with console.status("[bold cyan]Logging in to Instagram...[/]"):
            client = reels_mod.get_client(sessionid)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise SystemExit(1)
    except Exception as exc:
        if "challenge" in str(exc).lower():
            console.print(
                "[red]Instagram raised a login challenge.[/] Not retrying — resolve it "
                "in the app/browser, then refresh INSTAGRAM_SESSIONID in .env and "
                "delete ~/.ytk/instagram_session.json."
            )
        else:
            console.print(
                f"[red]Instagram login failed:[/] {exc}\n"
                "The session cookie may have expired — refresh INSTAGRAM_SESSIONID in "
                ".env and delete ~/.ytk/instagram_session.json."
            )
        raise SystemExit(1)

    peer = os.environ.get("INSTAGRAM_PEER") or None
    thread_desc = f"@{peer} thread" if peer else "note-to-self thread"
    state = reels_mod.ReelsState() if rebuild else reels_mod.load_state()
    with console.status(f"[bold cyan]Reading {thread_desc}...[/]"):
        new_state = reels_mod.refresh(client, state, peer=peer)

    pending = new_state.pending

    def _describe(item) -> str:
        date = item.shared_at or "----------"
        author = f"@{item.author}" if item.author else "?"
        return f"{date}  {author:<24}  {item.url}"

    if dry_run:
        if not pending:
            console.print(f"[dim]Nothing pending from the {thread_desc}.[/]")
            return
        console.print(f"[bold]{len(pending)}[/] pending link(s) — dry run, nothing ingested:")
        for item in pending:
            console.print(f"  {_describe(item)}")
        return

    # Persist discovery immediately: the cursor has advanced, pending is the record.
    reels_mod.save_state(new_state)

    if not pending:
        console.print(f"[dim]Nothing pending from the {thread_desc}.[/]")
        return

    if gallery:
        import webbrowser

        reels_mod.GALLERY_PATH.parent.mkdir(parents=True, exist_ok=True)
        reels_mod.GALLERY_PATH.write_text(reels_mod.gallery_html(pending), encoding="utf-8")
        webbrowser.open(reels_mod.GALLERY_PATH.as_uri())
        console.print(f"[cyan]Gallery opened:[/] {reels_mod.GALLERY_PATH}")

    if ingest_all:
        selected = pending[:limit] if limit is not None else list(pending)
        if len(selected) < len(pending):
            console.print(
                f"[yellow]Limiting to {len(selected)} of {len(pending)} pending links.[/]"
            )
    else:
        console.print(f"[bold]{len(pending)}[/] pending link(s):")
        for i, item in enumerate(pending, 1):
            console.print(f"  [bold cyan]{i:>3}[/]  {_describe(item)}")
        while True:
            raw = click.prompt("Ingest which? (e.g. 1,3,5-9 / all / none)", default="none")
            try:
                indices = reels_mod.parse_selection(raw, len(pending))
                break
            except ValueError as exc:
                console.print(f"[red]{exc}[/]")
        selected = [pending[i] for i in indices]
        if limit is not None:
            selected = selected[:limit]

    if not selected:
        console.print(f"[dim]Nothing selected — {len(pending)} link(s) remain pending.[/]")
        return

    ok = 0
    failed = 0
    for i, item in enumerate(selected, 1):
        console.rule(f"[bold]{i}/{len(selected)}[/] {item.url}")
        succeeded = False
        try:
            ctx.invoke(add, url=item.url)
            succeeded = True
        except SystemExit as exc:
            if exc.code in (0, None):
                succeeded = True
            else:
                console.print(f"[red]failed:[/] exited {exc.code}")
        except Exception as exc:
            console.print(f"[red]failed:[/] {exc}")

        if succeeded:
            ok += 1
            # drop from the queue and persist right away, so a crash mid-batch
            # never re-ingests; failures stay pending for a later retry
            new_state.pending.remove(item)
            reels_mod.save_state(new_state)
        else:
            failed += 1
        if i < len(selected):
            time.sleep(3)

    console.print(
        f"[green]{ok} ingested[/], [red]{failed} failed[/], "
        f"[dim]{len(new_state.pending)} pending[/]."
    )


@cli.command()
@click.argument("video_id")
@click.argument("query")
@click.option("-n", default=5, show_default=True, help="Number of results.")
@click.option(
    "--rerank/--no-rerank",
    default=None,
    help="Cross-encoder second stage (default: YTK_RERANK env).",
)
def dive(video_id: str, query: str, n: int, rerank: bool | None):
    """Segment-level semantic search within a specific video.

    VIDEO_ID is the YouTube video ID (e.g. dQw4w9WgXcQ).
    """
    from .store import search_segments  # deferred: chromadb costs ~330ms (#146)

    with console.status("[bold cyan]Searching segments...[/]"):
        results = search_segments(query, video_id=video_id, n=n, rerank=rerank)

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

        console.print(
            Panel(
                f"{preview}\n\n"
                f"[bold cyan]Timestamp[/]  [link={r.timestamp_url}]{timestamp}[/link]  "
                f"[bold cyan]Match[/] {match_pct}  "
                f"[bold cyan]URL[/] {r.timestamp_url}",
                title=f"[bold]{i}. @ {timestamp}[/]",
                box=box.ROUNDED,
            )
        )


@cli.command()
def auth():
    """Authenticate with YouTube Data API v3 (one-time OAuth flow)."""
    from urllib.parse import parse_qs, urlparse

    from google_auth_oauthlib.flow import InstalledAppFlow

    from .scheduler import _CLIENT_SECRETS, _SCOPES, _TOKEN_FILE

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
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print what would be synced without running the pipeline.",
)
@click.option(
    "-v/-q",
    "--verbose/--quiet",
    default=True,
    help="Step-by-step progress per video (default) vs. a spinner.",
)
def sync(dry_run: bool, verbose: bool):
    """Poll the 'ytk' YouTube playlist and ingest new videos."""
    from .scheduler import authenticate
    from .scheduler import sync as _sync

    cfg = load_config()

    with console.status("[bold cyan]Authenticating...[/]"):
        service = authenticate()

    verb = "dry-run" if dry_run else "syncing"
    status_cm = (
        console.status(f"[bold cyan]{verb.capitalize()} ytk playlist...[/]")
        if not verbose
        else _nullctx()
    )
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
@click.option("-n", default=25, show_default=True, help="Top tags to show.")
def tags(n: int):
    """Tag vocabulary health: distinct count + usage distribution.

    Watch the distinct count over time — vault-aware enrichment (issue #15)
    should flatten its growth as tags converge on canonical spellings.
    """
    from .store import tag_counts

    counts = tag_counts()
    if not counts:
        console.print("[yellow]No tags indexed yet.[/]")
        return
    total_uses = sum(counts.values())
    singletons = sum(1 for c in counts.values() if c == 1)
    console.print(
        f"[bold]{len(counts)}[/] distinct tags, {total_uses} uses, {singletons} used only once\n"
    )
    for tag, count in counts.most_common(n):
        console.print(f"  {count:>4}  [bold cyan]#{tag}[/]")


@cli.command()
@click.argument("query")
@click.option("-n", default=5, show_default=True, help="Number of results.")
@click.option(
    "--rerank/--no-rerank",
    default=None,
    help="Cross-encoder second stage (default: YTK_RERANK env).",
)
def search(query: str, n: int, rerank: bool | None):
    """Semantic search across ingested videos."""
    from .store import search_videos  # deferred: chromadb costs ~330ms (#146)

    with console.status("[bold cyan]Searching...[/]"):
        results = search_videos(query, n=n, rerank=rerank)

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

        body = (
            f"{thesis_line}\n\n{summary_preview}\n\n{meta_line}"
            if thesis_line
            else f"{summary_preview}\n\n{meta_line}"
        )
        console.print(
            Panel(
                body,
                title=f"[bold]{i}. {r.title}[/]",
                box=box.ROUNDED,
            )
        )


@cli.command(name="eval")
@click.option(
    "--update-baseline",
    "update_baseline",
    is_flag=True,
    default=False,
    help="Re-stamp eval/retrieval/baseline.json from this run.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Print the raw report as JSON instead of tables.",
)
@click.option("--top-k", default=10, show_default=True, help="Ranking window for hit@k.")
def eval_cmd(update_baseline: bool, as_json: bool, top_k: int):
    """Run the retrieval regression gate against the live store.

    Scores the frozen known-item query set through the production search
    paths and fails (exit 1) if hit rates regressed past the baseline's
    tolerance. The measuring stick for any change to search behavior.
    """
    import json as _json
    from datetime import date

    from . import retrieval_gate
    from .store import EMBEDDING_EPOCH

    # in --json mode stdout is the report and nothing else; all human chrome
    # (spinner, verdicts) moves to stderr so pipes get parseable output
    out = Console(stderr=True) if as_json else console

    # Re-stamping pins the scoring surface to the corpus as it stands right
    # now, before the run, so the gate measures against exactly what it
    # freezes (#111). Growth after this point is simply not scored.
    if update_baseline:
        frozen = retrieval_gate.snapshot_frozen_ids()
        retrieval_gate.write_frozen_corpus(frozen)
        out.print(
            f"[green]Frozen corpus stamped:[/] {len(frozen)} docs -> "
            f"{retrieval_gate.FROZEN_CORPUS_PATH}"
        )

    with out.status("[bold cyan]Running retrieval gate (embedding queries)...[/]"):
        report = retrieval_gate.run_live_gate(top_k=top_k)

    if as_json:
        click.echo(_json.dumps(report, indent=2))
    else:
        table = Table("bucket", "n", "hit@1", "hit@5", "hit@10", box=box.SIMPLE)
        for bucket, row in report["per_bucket"].items():
            table.add_row(bucket, str(row["n"]), *(f"{row[f'hit@{k}']:.3f}" for k in (1, 5, 10)))
        o = report["overall"]
        table.add_row(
            "[bold]overall[/]",
            str(report["n_evaluated"]),
            *(f"[bold]{o[f'hit@{k}']:.3f}[/]" for k in (1, 5, 10)),
        )
        out.print(table)
        if "graded" in report:
            graded = report["graded"]
            out.print(
                f"graded nDCG@10: [bold]{graded['ndcg@10']:.3f}[/]  "
                f"label coverage: {graded['label_coverage']:.1%}  "
                f"judge: {graded['judge']['model']} / "
                f"{graded['judge']['prompt_version']}"
            )
            if graded["unjudged_pairs"]:
                out.print(
                    f"[yellow]{len(graded['unjudged_pairs'])} new result pairs "
                    "need judging before nDCG is a closed comparison[/]"
                )
        prov = report.get("provenance") or {}
        if prov.get("frozen_corpus_size"):
            grown = (prov.get("collection_counts") or {}).values()
            out.print(
                f"[dim]scored against {prov['frozen_corpus_size']} frozen docs "
                f"(live store: {sum(grown)}); fetch window {report.get('fetch_k', top_k)}[/]"
            )
        if report.get("freeze_starved"):
            out.print(
                f"[yellow]{len(report['freeze_starved'])} queries had their frozen "
                "window starved by post-baseline documents[/] — re-stamp if this grows"
            )
        if report["missing_gold"]:
            out.print(
                f"[yellow]{len(report['missing_gold'])} gold docs missing from "
                f"the store[/] (excluded from rates):"
            )
            for gid in report["missing_gold"]:
                out.print(f"  [dim]{gid}[/]")

    if update_baseline:
        baseline = retrieval_gate.make_baseline(
            report, epoch=EMBEDDING_EPOCH, authored=date.today().isoformat()
        )
        retrieval_gate.BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        retrieval_gate.BASELINE_PATH.write_text(
            _json.dumps(baseline, indent=2) + "\n", encoding="utf-8"
        )
        out.print(f"[green]Baseline written:[/] {retrieval_gate.BASELINE_PATH}")
        return

    if not retrieval_gate.BASELINE_PATH.exists():
        out.print("[red]No baseline found.[/] Stamp one first: [bold]ytk eval --update-baseline[/]")
        raise SystemExit(2)

    baseline = _json.loads(retrieval_gate.BASELINE_PATH.read_text(encoding="utf-8"))
    if not as_json:
        deltas = "  ".join(
            f"{m}: {report['overall'][m] - baseline['overall'][m]:+.3f}"
            for m in ("hit@5", "hit@10")
        )
        out.print(f"vs baseline ({baseline['epoch']}, {baseline['authored']}): {deltas}")
    failures = retrieval_gate.compare_to_baseline(report, baseline)
    if failures:
        for f in failures:
            out.print(f"[red]GATE FAIL[/] {f}")
        raise SystemExit(1)
    out.print("[green]Gate passed.[/]")


@cli.command(name="profile")
@click.option(
    "--render-only",
    is_flag=True,
    help="Re-render profile.md from the latest snapshot, skipping clustering and the Claude call.",
)
@click.option(
    "--if-stale",
    "if_stale",
    type=int,
    default=None,
    metavar="N",
    help="Skip synthesis (exit 0) unless at least N notes were added since the last snapshot.",
)
def profile_cmd(render_only: bool, if_stale: int | None):
    """Synthesize a living interest profile from everything in the vault."""
    from .synthesis import SynthesisTooSparse, notes_since_snapshot, rerender_latest, run_profile

    if if_stale is not None and not render_only:
        delta, previous = notes_since_snapshot()
        if previous is not None and delta < if_stale:
            console.print(
                f"[yellow]Profile fresh enough:[/] {delta} new notes since "
                f"{previous.generated_at[:10]} (threshold {if_stale}). Skipping."
            )
            return

    try:
        if render_only:
            snapshot, path = rerender_latest()
        else:
            with console.status("[bold cyan]Clustering and synthesizing...[/]"):
                snapshot, path = run_profile()
    except SynthesisTooSparse as exc:
        console.print(
            f"[yellow]Vault too sparse:[/] {exc.have} notes "
            f"(need {exc.need}). Run [bold]ytk feed[/] or [bold]ytk sync[/] first."
        )
        raise SystemExit(1)
    except FileNotFoundError as exc:
        console.print(f"[yellow]Nothing to render:[/] {exc}")
        raise SystemExit(1)
    except Exception as exc:
        console.print(f"[red]Profile failed:[/] {exc}")
        raise SystemExit(1)

    console.print(f"[green]Profile written:[/] {path}")
    if snapshot.profile_score:
        score = snapshot.profile_score
        delta = f" ({score.delta:+.4f})" if score.delta is not None else ""
        console.print(
            f"[cyan]Profile ranking:[/] nDCG {score.score:.4f}{delta} · "
            f"{len(score.positive_ids)} held-out saves / "
            f"{len(score.negative_ids)} matched candidates"
        )
        if score.warning:
            console.print(f"[yellow]WARNING:[/] {score.warning}")
    else:
        console.print(
            "[yellow]Profile ranking unavailable:[/] no complete saved/pending visual cohort"
        )
    table = Table(
        box=box.SIMPLE, title=f"{len(snapshot.themes)} themes · {snapshot.note_count} notes"
    )
    table.add_column("Theme", style="cyan")
    table.add_column("Share", justify="right")
    table.add_column("Notes", justify="right")
    for t in snapshot.themes:
        table.add_row(t.label, f"{round(t.weight * 100)}%", str(len(t.note_ids)))
    console.print(table)


@cli.command(name="recap")
@click.option("-n", "count", type=int, default=12, help="How many recent ingests to consider.")
@click.option(
    "--context",
    "context_only",
    is_flag=True,
    help="Print the gathered material as markdown without the Claude synthesis "
    "(what the /whats-new skill consumes).",
)
def recap_cmd(count: int, context_only: bool):
    """Recap what was recently ingested and how it ties to your recent work."""
    from rich.markdown import Markdown

    from . import digest

    ctx = digest.gather_recent(n=count)
    if not ctx.ingests:
        console.print("[yellow]Nothing ingested yet.[/] Queue and ingest from the inbox first.")
        return
    if context_only:
        # Plain stdout, not rich: this output is piped into a Claude session.
        click.echo(digest.render_context(ctx))
        return
    with console.status("[bold cyan]Reading the vault and connecting the dots...[/]"):
        narrative = digest.synthesize(ctx)
    console.print(Markdown(narrative))


@cli.command(name="remember")
@click.argument("text", required=False, default="")
@click.option("--tags", "-t", default="", help="Comma-separated tags.")
def remember_cmd(text: str, tags: str):
    """Store a memory note in the vault and index it for semantic search.

    TEXT may be omitted to read from stdin: echo 'note' | ytk remember -t foo
    """
    from .store import similar_memories, upsert_memory
    from .vault import remember as _remember

    if not text:
        text = sys.stdin.read().strip()
    if not text:
        console.print("[red]No text provided.[/]")
        raise SystemExit(1)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        # neighbors queried before the write so the new note can't shadow them
        neighbors = [nb for nb in similar_memories(text, n=5) if nb.similarity >= 0.60]
        note_path, doc_id = _remember(text, tag_list)
        upsert_memory(doc_id, text, tag_list, str(note_path))
        console.print(f"[bold green]Memory stored:[/] {note_path}")
        if neighbors:
            console.print("[yellow]Similar existing memories:[/]")
            for nb in neighbors:
                console.print(f"  {nb.similarity:.0%}  {nb.source_path}", markup=False)
        console.print(LINK_REMINDER, style="dim", markup=False)
    except OSError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)


@cli.command(name="memo")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Record + transcribe + print proposed routing; execute nothing.",
)
@click.option("--text", default="", help="Skip recording/STT and route this text.")
@click.option(
    "--quick",
    is_flag=True,
    default=False,
    help="Popup mode: close as soon as audio is captured; transcribe and route in the background.",
)
@click.option(
    "--from-audio",
    "from_audio",
    type=click.Path(exists=True),
    default=None,
    hidden=True,
    help="Background worker: transcribe this wav, then route.",
)
@click.pass_context
def memo_cmd(ctx: click.Context, dry_run: bool, text: str, quick: bool, from_audio: str | None):
    """Voice memo: record, transcribe locally, route, notify.

    Exit codes: 0 routed; 2 transcript saved but routing failed; 1 capture/STT failure.
    """
    from datetime import datetime as _dt

    from .memo import StageLog

    run_id = _dt.now().strftime("%H%M%S")
    log = StageLog(run_id)
    cfg = load_config()
    log.mark("CONFIG_LOADED")

    if from_audio:
        audio_path = Path(from_audio)
        log.mark("FROM_AUDIO", audio_path.name)
        try:
            transcript = memo_transcribe(audio_path, cfg.whisper_model)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise SystemExit(1)
        log.mark("TRANSCRIBED", f"{len(transcript)} chars")
        if not transcript:
            memo_notify("empty transcription; audio kept", "failed", cfg.memo_notify or None)
            raise SystemExit(1)
        snippet = transcript if len(transcript) <= 90 else transcript[:87] + "..."
        memo_notify(snippet, "transcribed", cfg.memo_notify or None)
        log.mark("NOTIFY_TRANSCRIBED")
    elif text:
        transcript, audio_path = text, None
        log.mark("TEXT_MODE")
    else:
        try:
            from .memo import preload_model

            if not quick:
                preload_model(cfg.whisper_model)
                log.mark("PRELOAD_SPAWNED")
            console.print("[bold red]\u25cf rec[/bold red]  [dim]speak, then press Enter[/dim]")
            log.mark("RECORDING")
            audio_path = memo_record(
                AUDIO_DIR / f"{_dt.now().strftime('%Y%m%d-%H%M%S')}.wav",
                wait=lambda _prompt: input(""),
            )
            log.mark("RECORDED", audio_path.name)
            if quick and not dry_run:
                subprocess.Popen(
                    [sys.argv[0], "memo", "--from-audio", str(audio_path)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                log.mark("BG_WORKER_SPAWNED")
                memo_notify("captured — transcribing...", "captured", cfg.memo_notify or None)
                log.mark("POPUP_CLOSED")
                return
            with console.status(
                f"[cyan]transcribing[/] [dim]({cfg.whisper_model})[/dim]", spinner="dots"
            ):
                transcript = memo_transcribe(audio_path, cfg.whisper_model)
            log.mark("TRANSCRIBED", f"{len(transcript)} chars")
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise SystemExit(1)
        if not transcript:
            console.print(f"[red]Empty transcription; audio kept at[/] {audio_path}")
            raise SystemExit(1)

    console.print(
        Panel(transcript, title="[bold]transcript[/bold]", border_style="cyan", padding=(0, 1))
    )
    note_path = memo_write_note(transcript, audio_path)

    try:
        with console.status("[magenta]routing via Claude[/]", spinner="moon"):
            log.mark("ROUTING")
            result = memo_route(transcript, repos=cfg.github_repos or [])
        log.mark("ROUTED", result.kind)
    except Exception as exc:
        memo_finalize(note_path, "failed", [])
        memo_index(note_path, transcript, "failed")
        console.print(f"[yellow]Saved raw ({note_path.name}); routing failed:[/] {exc}")
        if not dry_run:
            memo_notify("saved raw, routing failed", "failed", cfg.memo_notify or None)
        raise SystemExit(2)

    if dry_run:
        console.print(f"[cyan]Would route as:[/] {result.kind} — {result.summary}")
        for item in result.items:
            console.print(f"  {item.suggested_route}: {item.title}")
        memo_finalize(note_path, f"dry-run:{result.kind}", [])
        return

    with console.status("[yellow]executing routes[/]", spinner="dots"):
        routed_lines = memo_execute(result, transcript, cfg.github_repos or [])
    log.mark("EXECUTED", f"{len(routed_lines)} routes")
    memo_finalize(note_path, result.kind, routed_lines)
    memo_index(note_path, transcript, result.kind)
    log.mark("INDEXED")
    memo_notify(result.summary, result.kind, cfg.memo_notify or None)
    log.mark("NOTIFIED")
    console.print(
        Panel(
            f"[bold]{result.summary}[/bold]",
            title=f"[green]\u2713 {result.kind}[/green]",
            border_style="green",
            padding=(0, 1),
        )
    )
    time.sleep(3)
    console.print(f"[bold green]{result.kind}:[/] {result.summary}")
    for line in routed_lines:
        console.print(f"  {line}")


@cli.command(name="reindex")
@click.option("--force", is_flag=True, default=False, help="Re-embed all files, ignoring cache.")
def reindex_cmd(force: bool):
    """Index all vault notes into ChromaDB for semantic search."""
    from .vault import _get_brain_path, reindex_vault_report

    try:
        _get_brain_path()
    except OSError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    label = "Re-indexing all vault notes..." if force else "Indexing changed vault notes..."
    with console.status(f"[bold cyan]{label}[/]"):
        report = reindex_vault_report(force=force)

    console.print(f"[bold green]Indexed:[/] {report.indexed} notes")
    # Always print the scope. "Indexed: 0" is ambiguous on its own -- it reads as
    # "nothing changed" when it can also mean "your tree was never in scope" (#147).
    console.print(f"[dim]{report.summary()}[/]")


@cli.command(name="graph")
@click.option(
    "--open",
    "open_browser",
    is_flag=True,
    default=False,
    help="Open graph.html in browser after building.",
)
@click.option(
    "--output", default=None, help="Output path for graph.html (default: ~/.ytk/graph.html)."
)
@click.option(
    "--threshold",
    default=0.75,
    show_default=True,
    type=float,
    help="Semantic similarity cutoff for edges.",
)
def graph_cmd(open_browser: bool, output: str | None, threshold: float):
    """Build a knowledge graph from all vault notes and export as interactive HTML."""
    import webbrowser

    from .graph import build_graph, detect_communities, export_html, export_json

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
    console.print(
        f"[bold green]Graph built:[/] {len(G.nodes)} nodes, {len(G.edges)} edges, {n_communities} communities"
    )
    console.print(f"  HTML: {html_path}")
    console.print(f"  JSON: {default_json}")

    if open_browser:
        webbrowser.open(f"file://{html_path.resolve()}")


@cli.command()
@click.argument("url")
@click.option("--force", is_flag=True, default=False, help="Skip interest-tag filter.")
@click.option("--note", default="", help="Your thought about this save; steers enrichment.")
def ingest(url: str, force: bool, note: str):
    """Fetch a web article, enrich with AI, and store in the vault."""
    from .ingest import enrich_web, fetch_web
    from .store import strip_frontmatter, upsert_doc
    from .vault import content_note_doc_id, write_web_note

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
        result = enrich_web(content, user_note=note)

    post_result = check_post_enrichment(result, cfg)
    if not _prompt_on_failures(post_result, force):
        raise SystemExit(0)

    console.print(Panel(f"[italic]{result.thesis}[/]", title="[bold]Thesis[/]", box=box.ROUNDED))
    console.print(Panel(result.summary, title="[bold]Summary[/]", box=box.ROUNDED))

    try:
        note_path = write_web_note(content.url, content.title, content.author, content.date, result)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        console.print(LINK_REMINDER, style="dim", markup=False)
        doc_id = content_note_doc_id(note_path)
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(
            doc_id,
            body,
            {
                "doc_id": doc_id,
                "tags": ", ".join(result.interest_tags),
                "source_path": str(note_path),
            },
        )
    except OSError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")


@cli.command(name="add-instagram")
@click.argument("url")
@click.option("--note", default="", help="Your thought about this save; steers enrichment.")
@click.option(
    "--refresh",
    is_flag=True,
    help="Re-ingest and atomically replace the existing note, preserving user tags and sections.",
)
def add_instagram(url: str, note: str = "", refresh: bool = False):
    """Fetch an Instagram post, analyze visually with AI, and store in the vault."""
    from .enrich import enrich_instagram, enrich_instagram_reel
    from .instagram import capture_reel_media, fetch_instagram
    from .store import strip_frontmatter, upsert_doc
    from .vault import (
        NoteAlreadyExists,
        content_note_doc_id,
        refresh_instagram_note,
        write_instagram_note,
    )
    from .vision import image_blocks

    cfg = load_config()

    with console.status("[bold cyan]Fetching Instagram post...[/]"):
        try:
            post = fetch_instagram(url)
        except ValueError as exc:
            console.print(f"[red]Fetch failed:[/] {exc}")
            raise SystemExit(1)

    is_video = post.media_kind == "video" or post.video_path is not None

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", no_wrap=True)
    info.add_column()
    info.add_row("Username", f"@{post.username}")
    info.add_row("Date", post.timestamp)
    info.add_row("Media", post.media_kind)
    if post.images:
        info.add_row("Images", str(len(post.images)))
    if post.caption:
        info.add_row("Caption", post.caption[:120])
    console.print(Panel(info, title="[bold]Instagram Post[/]", box=box.ROUNDED))

    capture = None
    if is_video:
        with console.status("[bold cyan]Extracting frames + transcribing with Whisper...[/]"):
            capture = capture_reel_media(post, whisper_model=cfg.whisper_model)
        for warning in capture.warnings:
            console.print(f"[yellow]Capture warning:[/] {warning}")
        console.print(
            f"[dim]Capture: {len(capture.frame_bytes)} frames, "
            f"transcript {capture.transcript_status} "
            f"({len(capture.transcript_segments)} segments)"
            + (f", {int(capture.duration)}s" if capture.duration else "")
            + "[/]"
        )
        blocks = image_blocks(frame_bytes=capture.frame_bytes)
    else:
        with console.status("[bold cyan]Preparing visual content...[/]"):
            blocks = image_blocks(urls=post.images or None, force_base64=True)

    with console.status("[bold cyan]Enriching with Claude Haiku...[/]"):
        try:
            # `capture is not None` rather than `is_video`: the two are set
            # together above, and this spelling is the one that carries.
            if capture is not None:
                result = enrich_instagram_reel(
                    caption=post.caption,
                    username=post.username,
                    duration=capture.duration,
                    frame_count=len(capture.frame_bytes),
                    transcript_segments=capture.transcript_segments,
                    transcript_status=capture.transcript_status,
                    visual_blocks=blocks or [],
                    user_note=note,
                )
            else:
                result = enrich_instagram(
                    caption=post.caption,
                    username=post.username,
                    slide_count=len(post.images),
                    visual_blocks=blocks or [],
                    user_note=note,
                )
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
        writer = refresh_instagram_note if refresh else write_instagram_note
        note_path = writer(
            post,
            result,
            transcript_segments=capture.transcript_segments if capture else None,
            transcript_status=capture.transcript_status if capture else None,
            frame_bytes=capture.frame_bytes if capture else None,
        )
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        console.print(LINK_REMINDER, style="dim", markup=False)
        doc_id = content_note_doc_id(note_path)
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(
            doc_id,
            body,
            {
                "doc_id": doc_id,
                "tags": ", ".join(result.interest_tags),
                "source_path": str(note_path),
            },
        )
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")
    except OSError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")


def _backfill_ingest(url: str) -> None:
    """Run the full add-instagram pipeline with --refresh for one URL.

    Module-level seam so backfill tests can stub the expensive pipeline.
    """
    cli.main(args=["add-instagram", url, "--refresh"], standalone_mode=False)


@cli.command(name="backfill-instagram-reels")
@click.option("--dry-run", "dry_run", is_flag=True, help="List qualifying notes without ingesting.")
@click.option("--apply", "apply_", is_flag=True, help="Refresh every qualifying note.")
def backfill_instagram_reels(dry_run: bool, apply_: bool):
    """Re-capture reel notes written before the capture schema existed.

    Discovery is structural (frontmatter + stored assets); each refresh runs
    the full pipeline one note at a time and failures never stop the loop.
    """
    from .vault import find_reel_backfill_candidates

    if not dry_run and not apply_:
        dry_run = True

    candidates = find_reel_backfill_candidates()
    if not candidates:
        console.print(
            "[green]No backfill candidates — all reel notes carry the current capture schema.[/]"
        )
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Note", overflow="fold")
    table.add_column("URL", overflow="fold")
    table.add_column("User")
    table.add_column("Why", overflow="fold")
    table.add_column("Transcript")
    table.add_column("Frames")
    for c in candidates:
        table.add_row(
            c["path"].name,
            c["url"],
            c["username"],
            c["reason"],
            "yes" if c["has_transcript"] else "no",
            "yes" if c["has_frames"] else "no",
        )
    console.print(table)
    console.print(f"[bold]{len(candidates)}[/] candidate(s)")

    if dry_run:
        console.print("[dim]Dry run — nothing ingested. Re-run with --apply to refresh.[/]")
        return

    succeeded, failed = [], []
    for c in candidates:
        console.print(f"\n[bold cyan]Refreshing[/] {c['url']}")
        try:
            _backfill_ingest(c["url"])
            succeeded.append(c)
        except (Exception, SystemExit) as exc:
            failed.append((c, exc))
            console.print(f"[red]Failed:[/] {c['url']} — {exc}")

    console.print(
        f"\n[bold]Backfill report:[/] {len(succeeded)} succeeded, "
        f"{len(failed)} failed, {len(candidates)} total"
    )
    for c, exc in failed:
        console.print(f"[red]  {c['url']}[/] — {exc}")


@cli.command(name="add-pinterest")
@click.argument("url")
@click.option("--note", default="", help="Your thought about this save; steers enrichment.")
def add_pinterest(url: str, note: str = ""):
    """Fetch a Pinterest pin, analyze the image with AI, and store in the vault."""
    from .enrich import enrich_instagram
    from .pinterest import fetch_pinterest
    from .store import strip_frontmatter, upsert_doc
    from .vault import NoteAlreadyExists, content_note_doc_id, write_pinterest_note
    from .vision import image_blocks

    with console.status("[bold cyan]Fetching pin...[/]"):
        try:
            pin = fetch_pinterest(url)
        except ValueError as exc:
            console.print(f"[red]Fetch failed:[/] {exc}")
            raise SystemExit(1)

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", no_wrap=True)
    info.add_column()
    info.add_row("Title", pin.title or "(untitled)")
    if pin.description:
        info.add_row("Description", pin.description[:120])
    console.print(Panel(info, title="[bold]Pinterest Pin[/]", box=box.ROUNDED))

    with console.status("[bold cyan]Analyzing image with AI...[/]"):
        try:
            blocks = image_blocks(urls=[pin.image_url], force_base64=True)
            result = enrich_instagram(
                caption=f"{pin.title}\n\n{pin.description}".strip(),
                username="pinterest",
                slide_count=1,
                visual_blocks=blocks,
                user_note=note,
            )
        except Exception as exc:
            console.print(f"[red]Enrichment failed:[/] {exc}")
            raise SystemExit(1)

    console.print(Panel(result.summary, title="[bold]Summary[/]", box=box.ROUNDED))

    try:
        note_path = write_pinterest_note(pin, result)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        console.print(LINK_REMINDER, style="dim", markup=False)
        doc_id = content_note_doc_id(note_path)
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(
            doc_id,
            body,
            {
                "doc_id": doc_id,
                "tags": ", ".join(result.interest_tags),
                "source_path": str(note_path),
            },
        )
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")
    except OSError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")


@cli.command(name="add-tiktok")
@click.argument("url")
@click.option("--note", default="", help="Your thought about this save; steers enrichment.")
def add_tiktok(url: str, note: str = ""):
    """Fetch a TikTok, transcribe + extract frames, and store in the vault."""
    from .enrich import enrich_tiktok
    from .store import strip_frontmatter, upsert_doc
    from .tiktok import fetch_tiktok, transcribe_tiktok
    from .vault import NoteAlreadyExists, content_note_doc_id, write_tiktok_note
    from .vision import download_video_temp, extract_frames, image_blocks

    cfg = load_config()

    with console.status("[bold cyan]Fetching TikTok metadata...[/]"):
        try:
            post = fetch_tiktok(url)
        except ValueError as exc:
            console.print(f"[red]Fetch failed:[/] {exc}")
            raise SystemExit(1)

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", no_wrap=True)
    info.add_column()
    info.add_row("Author", f"@{post.username}")
    info.add_row("Title", post.title or "[dim](none)[/]")
    info.add_row("Date", post.timestamp or "[dim](unknown)[/]")
    info.add_row("Duration", f"{post.duration}s")
    if post.view_count is not None:
        info.add_row("Views", f"{post.view_count:,}")
    if post.like_count is not None:
        info.add_row("Likes", f"{post.like_count:,}")
    if post.music:
        info.add_row("Music", post.music)
    console.print(Panel(info, title="[bold]TikTok[/]", box=box.ROUNDED))

    with console.status("[bold cyan]Transcribing audio with Whisper...[/]"):
        segments = transcribe_tiktok(url, whisper_model=cfg.whisper_model)
    transcript = " ".join(s["text"] for s in segments).strip()
    if transcript:
        preview = textwrap.fill(transcript[:600], width=80)
        console.print(
            Panel(
                preview,
                title=f"[bold]Transcript[/] [dim]({len(segments)} segs)[/dim]",
                box=box.ROUNDED,
            )
        )
    else:
        console.print("[dim]No transcribable speech detected.[/]")

    frame_bytes: list[bytes] = []
    visual_blocks: list[dict] | None = None
    video_tmp: Path | None = None
    try:
        with console.status("[bold cyan]Downloading video for frame extraction...[/]"):
            video_tmp = download_video_temp(url)
        with console.status("[bold cyan]Extracting frames...[/]"):
            frame_bytes = extract_frames(video_tmp, timestamps=[], baseline_n=6) or []
        if frame_bytes:
            visual_blocks = image_blocks(frame_bytes=frame_bytes)
    except Exception as exc:
        console.print(f"[yellow]Frame extraction failed:[/] {exc}")
    finally:
        if video_tmp is not None:
            video_tmp.unlink(missing_ok=True)

    with console.status("[bold cyan]Enriching with Claude...[/]"):
        try:
            result = enrich_tiktok(
                post={
                    "title": post.title,
                    "description": post.description,
                    "username": post.username,
                    "duration": post.duration,
                    "music": post.music,
                },
                transcript=transcript,
                visual_blocks=visual_blocks,
                user_note=note,
            )
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
        note_path = write_tiktok_note(
            post, result, transcript=transcript, frame_bytes=frame_bytes or None
        )
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        console.print(LINK_REMINDER, style="dim", markup=False)
        doc_id = content_note_doc_id(note_path)
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(
            doc_id,
            body,
            {
                "doc_id": doc_id,
                "tags": ", ".join(result.interest_tags),
                "source_path": str(note_path),
            },
        )
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")
    except OSError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")


@cli.command(name="tiktok-sync")
@click.option(
    "--pages",
    type=int,
    default=None,
    help="Cap intercepted favorite pages (default: walk everything).",
)
@click.option("--headed", is_flag=True, help="Show the Playwright browser window (debugging).")
def tiktok_sync(pages: int | None, headed: bool):
    """Sync TikTok favorites into the pending queue.

    Session replay: a headless Playwright Firefox scrolls your favorites tab
    with cookies read from Zen, and the signed API responses TikTok's own JS
    fetches are read off the wire. First run walks the whole backlog; later
    runs stop at the first already-seen video.
    """
    from . import reels, tiktok_fav
    from .config import load_config
    from .ui import hub

    cfg = load_config()
    if not cfg.tiktok_username:
        raise click.ClickException(
            "Set tiktok_username in ~/.ytk/config.yaml (your @handle, without the @)."
        )
    try:
        cookies = tiktok_fav.load_tiktok_cookies(tiktok_fav.zen_cookie_db())
    except tiktok_fav.TikTokAuthError as exc:
        raise click.ClickException(str(exc))

    state = reels.load_state()
    console.print(
        f"Scrolling @{cfg.tiktok_username} favorites ({len(state.tiktok_seen)} already seen)..."
    )
    try:
        fetched = tiktok_fav.fetch_favorites(
            cfg.tiktok_username,
            cookies,
            seen=frozenset(state.tiktok_seen),
            max_pages=pages,
            headed=headed,
        )
    except tiktok_fav.TikTokAuthError as exc:
        raise click.ClickException(str(exc))

    added = tiktok_fav.queue_new(state, fetched, extra_known=hub.ingested_urls())
    state.last_pulls["tiktok"] = time.time()
    reels.save_state(state)
    console.print(
        f"[green]{added} new favorites queued[/] "
        f"({len(state.pending)} pending total). Pick them at the hub /inbox."
    )


@cli.command(name="reddit-sync")
def reddit_sync():
    """Browse the allowlisted subreddits into the pending queue.

    Reads public subreddit listings as your logged-in session (cookie from
    Zen). Configure the allowlist in ~/.ytk/config.yaml under
    reddit_subreddits. Your saved posts are never read.
    """
    from . import reddit_feed, reels
    from .config import load_config
    from .ui import hub

    cfg = load_config()
    if not cfg.reddit_subreddits:
        raise click.ClickException(
            "No subreddits configured. Add a reddit_subreddits list to "
            "~/.ytk/config.yaml (e.g. [TouchDesigner, LocalLLaMA])."
        )
    try:
        cookie = reddit_feed.reddit_cookie_header()
    except reddit_feed.RedditAuthError as exc:
        raise click.ClickException(str(exc))

    state = reels.load_state()
    console.print(
        f"Browsing {len(cfg.reddit_subreddits)} subreddits "
        f"({cfg.reddit_sort}/{cfg.reddit_window})..."
    )
    added = reddit_feed.sync_subreddits(
        state,
        cookie,
        cfg.reddit_subreddits,
        sort=cfg.reddit_sort,
        window=cfg.reddit_window,
        limit=cfg.reddit_limit,
        extra_known=hub.ingested_urls(),
    )
    state.last_pulls["reddit"] = time.time()
    reels.save_state(state)
    console.print(
        f"[green]{added} new posts queued[/] "
        f"({len(state.pending)} pending total). Pick them at the hub /inbox."
    )


@cli.command(name="reddit-discover")
@click.argument("topic")
@click.option("-n", "--limit", type=int, default=10, help="Max suggestions.")
def reddit_discover(topic: str, limit: int):
    """Find subreddits related to a topic to add to your allowlist.

    Uses Reddit's own subreddit search. Copy the ones you want into
    reddit_subreddits in ~/.ytk/config.yaml.
    """
    from . import reddit_feed

    try:
        cookie = reddit_feed.reddit_cookie_header()
    except reddit_feed.RedditAuthError as exc:
        raise click.ClickException(str(exc))

    cfg = load_config()
    current = {s.lower() for s in cfg.reddit_subreddits}
    hits = reddit_feed.search_subreddits(topic, cookie, limit=limit)
    if not hits:
        console.print(f"No subreddits found for '{topic}'.")
        return
    for h in hits:
        mark = "[dim](in allowlist)[/]" if h["name"].lower() in current else ""
        nsfw = "[red]nsfw[/] " if h["over_18"] else ""
        console.print(
            f"  [bold]r/{h['name']}[/]  {h['subscribers']:,} subs {nsfw}{mark}\n"
            f"    [dim]{h['description'][:90]}[/]"
        )


@cli.command(name="add-reddit")
@click.argument("url")
@click.option("--note", default="", help="Your thought about this save; steers enrichment.")
def add_reddit(url: str, note: str = ""):
    """Ingest one Reddit post (self-text or link) with its top comments."""
    from .config import load_config
    from .enrich import enrich_content
    from .reddit_feed import (
        RedditAuthError,
        build_content_block,
        external_video_url,
        fetch_comments,
        post_from_thread,
        reddit_cookie_header,
        top_comments,
    )
    from .store import strip_frontmatter, upsert_doc
    from .vault import _cross_link_notes, content_note_doc_id, write_reddit_note

    try:
        cookie = reddit_cookie_header()
        thread = fetch_comments(url, cookie)
    except RedditAuthError as exc:
        raise click.ClickException(str(exc))
    post = post_from_thread(thread)
    if not post:
        raise click.ClickException(f"Could not parse a Reddit post from {url}")

    comments = top_comments(thread)
    block = build_content_block(post, comments)
    cfg = load_config()

    with console.status("[bold cyan]Enriching with Claude...[/]"):
        result = enrich_content(block, "reddit", user_note=note, tone=cfg.hub.enrich_tone)

    console.print(Panel(f"[italic]{result.thesis}[/]", title="[bold]Thesis[/]", box=box.ROUNDED))
    console.print(Panel(result.summary, title="[bold]Summary[/]", box=box.ROUNDED))

    try:
        note_path = write_reddit_note(post, result, comments)
        console.print(f"\n[bold green]Note written:[/] {note_path}")
        console.print(LINK_REMINDER, style="dim", markup=False)
        doc_id = content_note_doc_id(note_path)
        body = strip_frontmatter(note_path.read_text(encoding="utf-8"))
        upsert_doc(
            doc_id,
            body,
            {
                "doc_id": doc_id,
                "tags": ", ".join(result.interest_tags),
                "source_path": str(note_path),
            },
        )

        video_url = external_video_url(post)
        if video_url:
            from . import db, hydrate

            vid = hydrate.youtube_video_id(video_url)
            if vid and not db.is_processed(vid):
                ctx = click.get_current_context()
                ctx.invoke(add, url=video_url, note=note)
            _cross_link_notes(note_path, video_url)
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")


@cli.command(name="recs-refresh")
@click.option(
    "--unresolved-only",
    is_flag=True,
    help="Only retry entries that never resolved; skip metadata backfill of resolved ones.",
)
def recs_refresh(unresolved_only: bool):
    """Re-resolve stored recs against TMDb / AniList / Google Books.

    Retries every unresolved entry (a failed resolution is otherwise permanent
    — record() only re-tries a title when a new note mentions it) and
    backfills fields added since an entry was stored, such as genres.
    Preserves status, sources, and first_seen; merges an entry that resolves
    into an existing canonical twin.
    """
    from ytk import recs

    with console.status("[cyan]Re-resolving recs...[/]"):
        summary = recs.refresh(only_unresolved=unresolved_only)
    console.print(
        f"[green]Refreshed[/] {summary['total']} entries: "
        f"{summary['resolved']} resolved, {summary['still_unresolved']} still unresolved, "
        f"{summary['merged']} merged into canonical twins "
        f"({summary['total_after']} entries now)."
    )


@cli.command(name="recs-backfill")
@click.option("--limit", type=int, default=None, help="Scan at most N unscanned notes this run.")
@click.option(
    "--all", "rescan_all", is_flag=True, help="Re-scan every note, ignoring the scanned set."
)
def recs_backfill(limit: int | None, rescan_all: bool):
    """Scan existing notes for movie/show/anime/book/manga recs and resolve them.

    Runs the recommendation extractor over each note body, resolves titles via
    TMDb / AniList / Open Library, and merges into ~/.ytk/recs.json. Idempotent:
    scanned notes are tracked so re-runs only touch new ones (unless --all).
    """
    import json as _json

    from ytk import recs, vault
    from ytk.store import strip_frontmatter

    brain = vault._get_brain_path()
    sources = brain / "sources"
    notes = sorted(sources.glob("**/*.md")) if sources.exists() else []
    scanned_path = Path.home() / ".ytk" / "recs-scanned.json"
    scanned: set[str] = set()
    if scanned_path.exists() and not rescan_all:
        try:
            scanned = set(_json.loads(scanned_path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            scanned = set()

    todo = [md for md in notes if rescan_all or str(md.relative_to(brain.parent)) not in scanned]
    if limit:
        todo = todo[:limit]
    if not todo:
        console.print("[green]Nothing to scan[/] — all notes already processed.")
        return

    found = 0
    with console.status(f"[cyan]Scanning {len(todo)} notes for recs...[/]") as status:
        for i, md in enumerate(todo, 1):
            rel = str(md.relative_to(brain.parent))
            status.update(f"[cyan]{i}/{len(todo)}[/] {md.stem[:50]}  ·  {found} recs so far")
            try:
                body = strip_frontmatter(md.read_text(encoding="utf-8"))
                for r in recs.extract_recommendations(body[:12000]):
                    entry = recs.record(r["kind"], r["title"], r.get("creator"), rel)
                    if entry:
                        found += 1
            except Exception as exc:
                console.print(f"[yellow]skip {md.stem}:[/] {exc}")
            scanned.add(rel)
            if i % 10 == 0:
                scanned_path.parent.mkdir(parents=True, exist_ok=True)
                scanned_path.write_text(_json.dumps(sorted(scanned)), encoding="utf-8")

    scanned_path.parent.mkdir(parents=True, exist_ok=True)
    scanned_path.write_text(_json.dumps(sorted(scanned)), encoding="utf-8")
    total = len(recs.entries())
    console.print(
        f"[bold green]Done[/] — {found} recommendations recorded, {total} titles in the store."
    )


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
@click.option(
    "--since",
    default=None,
    metavar="DATE",
    help="Start date: YYYY-MM-DD, 'today', 'yesterday', or 'N days ago'.",
)
@click.option(
    "--until",
    default=None,
    metavar="DATE",
    help="End date: YYYY-MM-DD, 'today', 'yesterday', or 'N days ago'.",
)
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
    from .imessage import enrich_journal, export_conversation, find_exported_file, parse_txt
    from .store import strip_frontmatter, upsert_doc
    from .vault import NoteAlreadyExists, content_note_doc_id, write_journal_note

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

    written_path: Path | None = None
    try:
        written_path = write_journal_note(thread, result)
        console.print(f"\n[bold green]Note written:[/] {written_path}")
        console.print(LINK_REMINDER, style="dim", markup=False)
        doc_id = content_note_doc_id(written_path)
        body = strip_frontmatter(written_path.read_text(encoding="utf-8"))
        upsert_doc(
            doc_id,
            body,
            {
                "doc_id": doc_id,
                "tags": ", ".join(result.interest_tags),
                "source_path": str(written_path),
            },
        )
    except NoteAlreadyExists as exc:
        console.print(f"\n[yellow]Note already exists:[/] {exc}")
    except OSError as exc:
        console.print(f"\n[yellow]Vault not configured:[/] {exc}")

    if written_path and written_path.exists():
        from .triage import extract_action_items

        cfg = load_config()
        vault_raw = os.environ.get("OBSIDIAN_VAULT_PATH", "")
        if vault_raw:
            vault_p = Path(vault_raw).expanduser()
            inbox = vault_p / "second-brain" / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            ideas_path = inbox / "ideas.md"
            review_path = inbox / "review.md"
            note_text = written_path.read_text(encoding="utf-8")
            with console.status("[bold cyan]Extracting action items...[/]"):
                items = extract_action_items(note_text, repos=cfg.github_repos or None)
            if not items:
                console.print("[dim]No actionable items found.[/]")
            else:
                summary = Table("", "Title", "Priority", "Route", box=box.SIMPLE, show_header=True)
                for idx, item in enumerate(items, 1):
                    pc = _PRIORITY_COLOR[item.priority]
                    repo_hint = f" ({item.suggested_repo})" if item.suggested_repo else ""
                    summary.add_row(
                        str(idx),
                        item.title,
                        f"[{pc}]{item.priority}[/]",
                        _ROUTE_LABEL[item.suggested_route] + repo_hint,
                    )
                console.print(
                    Panel(summary, title=f"[bold]{len(items)} Action Items[/]", box=box.ROUNDED)
                )
                for item in items:
                    if item.suggested_route == "gh-issue":
                        url = _triage_create_gh(item, cfg, console)
                        if url:
                            console.print(f"  [green]GH:[/] {item.title}  [dim]{url}[/]")
                        else:
                            console.print(
                                f"  [yellow]GH skipped (no repo configured):[/] {item.title}"
                            )
                    elif item.suggested_route == "idea":
                        with ideas_path.open("a", encoding="utf-8") as f:
                            f.write(f"\n- [ ] {item.title}\n  {item.description}\n")
                        console.print(f"  [cyan]Idea:[/] {item.title}")
                    else:
                        date_str = datetime.now().strftime("%Y-%m-%d")
                        with review_path.open("a", encoding="utf-8") as f:
                            f.write(
                                f"\n- [ ] {item.title} — *{written_path.stem}* ({date_str})\n  {item.description}\n"
                            )
                        console.print(f"  [magenta]Review:[/] {item.title}")


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
        [
            "gh",
            "issue",
            "create",
            "--title",
            item.title,
            "--body",
            item.description,
            "--repo",
            repo,
        ],
        capture_output=True,
        text=True,
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
            str(i),
            item.title,
            f"[{pc}]{item.priority}[/]",
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
                entry = (
                    f"\n- [ ] {item.title} — *{target.stem}* ({date_str})\n  {item.description}\n"
                )
                with review_path.open("a", encoding="utf-8") as f:
                    f.write(entry)
                console.print(f"  [magenta]Review:[/] {item.title}")
                routed["review"] += 1
    else:
        for i, item in enumerate(items, 1):
            pc = _PRIORITY_COLOR[item.priority]
            rl = _ROUTE_LABEL[item.suggested_route]
            default_choice = _ROUTE_DEFAULT[item.suggested_route]

            console.print(
                Panel(
                    f"[bold]{item.title}[/]\n\n{item.description}\n\n"
                    f"Priority: [{pc}]{item.priority}[/]  Suggested: [cyan]{rl}[/]",
                    title=f"[bold]{i}/{len(items)}[/]",
                    box=box.ROUNDED,
                )
            )
            console.print("  [1] GH issue  [2] Inbox/ideas  [3] Review  [4] Skip")

            while True:
                choice = click.prompt(
                    "  Route",
                    default=default_choice,
                    type=click.Choice(["1", "2", "3", "4"]),
                    show_choices=False,
                )

                if choice == "1":
                    if not cfg.github_repos:
                        console.print(
                            "  [yellow]No repos configured. Add github_repos to ~/.ytk/config.yaml[/]"
                        )
                        continue
                    if item.suggested_repo and item.suggested_repo in cfg.github_repos:
                        repo = item.suggested_repo
                        console.print(f"  [cyan]Auto-selected:[/] {repo}")
                    else:
                        for j, repo_opt in enumerate(cfg.github_repos, 1):
                            console.print(f"    [{j}] {repo_opt}")
                        repo_idx = (
                            click.prompt(
                                "  Repo",
                                type=click.IntRange(1, len(cfg.github_repos)),
                                default=1,
                            )
                            - 1
                        )
                        repo = cfg.github_repos[repo_idx]
                    gh_result = subprocess.run(
                        [
                            "gh",
                            "issue",
                            "create",
                            "--title",
                            item.title,
                            "--body",
                            item.description,
                            "--repo",
                            repo,
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if gh_result.returncode == 0:
                        console.print(f"  [green]Issue created:[/] {gh_result.stdout.strip()}")
                        routed["gh"] += 1
                        break
                    console.print(f"  [red]gh failed:[/] {gh_result.stderr.strip()}")
                    continue

                if choice == "2":
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

                if choice == "3":
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    entry = f"\n- [ ] {item.title} — *{target.stem}* ({date_str})\n  {item.description}\n"
                    with review_path.open("a", encoding="utf-8") as f:
                        f.write(entry)
                    console.print("  [green]Added to inbox/review.md[/]")
                    routed["review"] += 1
                    break

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
@click.option(
    "--prune",
    type=int,
    default=None,
    metavar="DAYS",
    help="Archive memories older than N days and remove from ChromaDB.",
)
@click.option(
    "--refresh-projects",
    is_flag=True,
    default=False,
    help="Re-run seed for project memories older than 30 days.",
)
@click.option(
    "--prune-audio",
    type=int,
    default=None,
    metavar="DAYS",
    help="Delete YouTube transcription-cache audio (yt_*) older than N days.",
)
@click.option("--dry-run", is_flag=True, default=False)
def gc(prune: int | None, refresh_projects: bool, prune_audio: int | None, dry_run: bool):
    """Manage vault memory lifecycle — list ages, prune stale entries, refresh projects."""
    import subprocess

    from .store import delete_doc, orphaned_memory_vectors
    from .vault import _get_brain_path, vault_note_doc_id

    def report_orphans() -> None:
        orphans = orphaned_memory_vectors()
        if not orphans:
            console.print("[green]memory vectors:[/] 0 orphaned source paths")
            return
        console.print(
            f"[yellow]memory vectors:[/] {len(orphans)} orphaned vector(s); "
            "stored text may be the last copy, so none were deleted"
        )
        for row in orphans[:10]:
            source = row["source_path"] or "(missing source_path metadata)"
            console.print(f"  [dim]{row['vector_id']} -> {source}[/]")
        if len(orphans) > 10:
            console.print(f"  [dim]... and {len(orphans) - 10} more[/]")

    did_audio = False
    if prune_audio is not None:
        from . import transcript

        removed = transcript.prune_audio_cache(max_age_days=prune_audio, dry_run=dry_run)
        verb = "would remove" if dry_run else "removed"
        console.print(
            f"[cyan]audio cache:[/] {verb} {len(removed)} yt_* file(s) older than {prune_audio}d"
        )
        did_audio = True

    try:
        vault_path = _get_brain_path()
    except OSError as exc:
        # A standalone audio prune (e.g. the nightly job) must not fail just
        # because the vault is unconfigured — the audio work already succeeded.
        if did_audio:
            return
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    mem_dir = vault_path / "inbox" / "memories"
    if not mem_dir.exists() or not list(mem_dir.glob("*.md")):
        console.print("[yellow]No memories found.[/]")
        report_orphans()
        return

    # Ages come from the note's own capture stamp, never mtime (R5/#150): one
    # sync event restamped 3,343 mtimes on 2026-05-02, so mtime ages are noise.
    from .vault import note_capture_date, stale_memories

    now = datetime.now()
    notes = sorted(mem_dir.glob("*.md"), key=note_capture_date)

    table = Table("File", "Age", "Tags", box=box.SIMPLE, show_header=True)
    for p in notes:
        age_days = (now - note_capture_date(p)).days
        content = p.read_text(encoding="utf-8")
        tag_match = re.search(r"^tags:\s*\n((?:  - .+\n)*)", content, re.MULTILINE)
        tags = ", ".join(re.findall(r"  - (.+)", tag_match.group(1))) if tag_match else ""
        table.add_row(p.name[:55], f"{age_days}d", tags[:45])
    console.print(Panel(table, title=f"[bold]Memories ({len(notes)})[/]", box=box.ROUNDED))

    if prune is not None:
        to_archive = stale_memories(mem_dir, days=prune, now=now)
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
                    delete_doc(vault_note_doc_id(p, vault_path, content))
                    p.rename(archive_dir / p.name)
                    console.print(f"  [dim]archived:[/] {p.name}")
                console.print(f"\n[bold green]Archived {len(to_archive)} memories.[/]")

    if refresh_projects:
        proj_mems = [p for p in notes if "project-context" in p.read_text(encoding="utf-8")]
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

    report_orphans()


@cli.command(name="index")
def index_cmd():
    """Rebuild wiki/index.md by scanning the vault from scratch."""
    from .vault import _get_brain_path, rebuild_index

    try:
        vault_path = _get_brain_path()
    except OSError as exc:
        console.print(f"[red]Vault not configured:[/] {exc}")
        raise SystemExit(1)

    with console.status("[bold cyan]Rebuilding index...[/]"):
        rebuild_index()

    console.print(f"[bold green]Index rebuilt:[/] {vault_path / 'wiki' / 'index.md'}")


@cli.command()
def dashboard():
    """Generate the rolling inbox/dashboard.md vault snapshot."""
    from .vault import _get_brain_path, write_raw

    try:
        vault_path = _get_brain_path()
    except OSError as exc:
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
            p
            for p in sorted(mem_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if datetime.fromtimestamp(p.stat().st_mtime) >= cutoff
        ]
        if recent:
            rows = "\n".join(f"- [[second-brain/inbox/memories/{p.stem}]]" for p in recent)
            sections.append(f"## Recent Memories (last 7 days)\n{rows}\n")

    # Recent videos
    youtube_dir = vault_path / "sources" / "youtube"
    if youtube_dir.exists():
        recent_videos = sorted(
            youtube_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:10]
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
                    proj_rows.append(
                        f"- **{proj.name}** — [[second-brain/projects/{proj.name}/{briefs[0].stem}]]"
                    )
        if proj_rows:
            sections.append("## Active Projects\n" + "\n".join(proj_rows) + "\n")

    # Inbox items (exclude old dated snapshots and the dashboard itself)
    inbox_dir = vault_path / "inbox"
    if inbox_dir.exists():
        inbox_items = [
            p
            for p in sorted(inbox_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not p.stem.startswith("review-") and p.stem != "dashboard"
        ]
        if inbox_items:
            rows = "\n".join(f"- [[second-brain/inbox/{p.stem}]]" for p in inbox_items)
            sections.append(f"## Inbox\n{rows}\n")

    content = "\n".join(sections)
    rel_path = "second-brain/inbox/dashboard.md"
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

    # Write a wrapper script so the plist never shell-interpolates the binary path
    script_path = Path.home() / ".ytk" / "nightly.sh"
    # touch last-sync-ok on success: the hub's catch-up sync (#90) only fires
    # when this marker is stale, so a good nightly suppresses the retry
    script_path.write_text(
        f'#!/bin/sh\n{ytk_bin} sync && touch "$HOME/.ytk/last-sync-ok" && '
        f"{ytk_bin} index && {ytk_bin} dashboard\n"
        f"{ytk_bin} gc --prune-audio 30\n",
        encoding="utf-8",
    )
    script_path.chmod(0o700)

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
        <string>{script_path}</string>
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


@cli.command(name="autoingest")
@click.option("--count", type=int, default=None, help="Max items to pull (hard-capped).")
@click.option("--dry-run", is_flag=True, help="Show what would be ingested without ingesting.")
def autoingest_cmd(count: int | None, dry_run: bool):
    """Ingest a small, profile-matched batch of pending items, stratified by theme.

    Scores pending items that carry text against your interest-profile theme
    centroids, spreads the pick across themes, boosts loved creators and skips
    muted ones, then ingests the top batch (tagged `auto-ingested`).
    """
    from ytk.autoingest import run_autoingest

    report = run_autoingest(count=count, dry_run=dry_run)
    if report.get("error"):
        raise click.ClickException(report["error"])

    console.print(
        f"[bold]{len(report['selected'])} selected[/] from {report['candidates']} "
        f"scorable pending items" + (" [yellow](dry run)[/]" if dry_run else "")
    )
    for p in report["selected"]:
        console.print(
            f"  [cyan]{p['score']:+.3f}[/] [dim]{p['source']:9}[/] {p['title']}  [dim]-> {p['theme']}[/]"
        )
    if not dry_run:
        msg = f"[green]{len(report['ingested'])} ingested[/]"
        if report.get("failures"):
            msg += f", [red]{len(report['failures'])} failed[/]"
        console.print(msg)


@cli.group(name="autoingest-schedule")
def autoingest_schedule():
    """Manage the scheduled profile-matched auto-ingest job."""


@autoingest_schedule.command(name="install")
@click.option("--weekday", default=0, show_default=True, help="Day for weekly runs (0=Sun..6=Sat).")
@click.option("--hour", default=7, show_default=True, help="Hour (0-23) to run.")
@click.option("--count", type=int, default=None, help="Items per run (defaults to config).")
def autoingest_schedule_install(weekday: int, hour: int, count: int | None):
    """Install a launchd job that runs `ytk autoingest` on a schedule.

    Cadence follows config.autoingest_cadence (daily | weekly); weekly runs on
    the given weekday, daily every day at the given hour.
    """
    ytk_bin = shutil.which("ytk")
    if not ytk_bin:
        console.print("[red]ytk binary not found in PATH.[/] Run [bold]uv tool install .[/] first.")
        raise SystemExit(1)

    cadence = load_config().autoingest_cadence.lower()
    log_path = Path.home() / ".ytk" / "autoingest.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    args = [ytk_bin, "autoingest"]
    if count is not None:
        args += ["--count", str(count)]
    args_xml = "\n".join(f"        <string>{a}</string>" for a in args)

    weekday_xml = (
        ""
        if cadence == "daily"
        else f"""        <key>Weekday</key>
        <integer>{weekday}</integer>
"""
    )
    plist_label = "com.ytk.autoingest"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{plist_label}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(
        f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{plist_label}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>StartCalendarInterval</key>
    <dict>
{weekday_xml}        <key>Hour</key>
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
""",
        encoding="utf-8",
    )
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    when = "daily" if cadence == "daily" else f"weekly (day {weekday})"
    console.print(f"[bold green]Installed:[/] {plist_path}")
    console.print(f"Runs {when} at [bold]{hour:02d}:00[/]. Logs: {log_path}")


@autoingest_schedule.command(name="uninstall")
def autoingest_schedule_uninstall():
    """Remove the auto-ingest launchd job."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.ytk.autoingest.plist"
    if not plist_path.exists():
        console.print("[yellow]No plist found.[/] Nothing to uninstall.")
        return
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    plist_path.unlink()
    console.print(f"[bold green]Uninstalled:[/] {plist_path}")


_CHROMA_LABEL = "com.ytk.chroma"
_CHROMA_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{_CHROMA_LABEL}.plist"
_CHROMA_LOG = Path.home() / ".ytk" / "logs" / "chroma.log"


@cli.group(name="chroma")
def chroma_command():
    """Run and manage the local Chroma server."""


@chroma_command.command(name="serve")
def chroma_serve():
    """Run the local Chroma server in the foreground."""
    from .chroma_runtime import runtime_config, server_arguments  # deferred: chromadb (#146)

    cfg = runtime_config()
    executable = Path(sys.executable).with_name("chroma")
    if not executable.is_file():
        raise click.ClickException(f"Chroma executable not found at {executable}")
    cfg.server_path.mkdir(parents=True, exist_ok=True)
    args = server_arguments(cfg, executable)
    os.execv(str(executable), args)


@chroma_command.command(name="install")
def chroma_install():
    """Install Chroma as an always-on loopback launchd agent."""
    from .chroma_runtime import launchd_plist, runtime_config  # deferred: chromadb (#146)

    ytk_bin = shutil.which("ytk")
    if not ytk_bin:
        raise click.ClickException("ytk binary not found; run `uv tool install --reinstall .`")
    cfg = runtime_config()
    _CHROMA_LOG.parent.mkdir(parents=True, exist_ok=True)
    _CHROMA_PLIST.parent.mkdir(parents=True, exist_ok=True)
    _CHROMA_PLIST.write_text(
        launchd_plist(cfg, ytk_bin=Path(ytk_bin), log_path=_CHROMA_LOG),
        encoding="utf-8",
    )
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{_CHROMA_LABEL}"],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(_CHROMA_PLIST)],
        check=True,
    )
    console.print(f"[green]Installed:[/] {_CHROMA_PLIST}")
    console.print(f"Chroma: http://{cfg.host}:{cfg.port}  Data: {cfg.server_path}")


@chroma_command.command(name="migrate")
@click.option("--resume", is_flag=True, help="Resume an interrupted migration safely.")
@click.option(
    "--batch-size",
    type=click.IntRange(min=1),
    default=256,
    show_default=True,
    help="Records copied per request.",
)
def chroma_migrate(resume: bool, batch_size: int):
    """Copy healthy legacy collections into the local Chroma server."""
    from .chroma_migrate import (  # deferred: chromadb costs ~330ms (#146)
        copy_collections,
        create_migration_clients,
        write_report,
    )
    from .chroma_runtime import runtime_config

    cfg = runtime_config()
    if cfg.mode != "http":
        raise click.ClickException("CHROMA_URL must select the local Chroma HTTP server")
    if os.environ.get("YTK_VISUAL_INDEX", "on").strip().lower() != "off":
        raise click.ClickException("set YTK_VISUAL_INDEX=off before migrating")
    if cfg.legacy_path.resolve() == cfg.server_path.resolve():
        raise click.ClickException("CHROMA_PATH and CHROMA_SERVER_PATH must be different")

    source, target = create_migration_clients(cfg)
    report = copy_collections(
        source,
        target,
        resume=resume,
        batch_size=batch_size,
    )
    report_path = write_report(report, Path.home() / ".ytk" / "recovery")
    for name, count in report.collections.items():
        console.print(f"{name}: {count}")
    console.print(f"[green]Migration complete:[/] {report_path}")


@chroma_command.command(name="restart")
def chroma_restart():
    """Restart the local Chroma launchd agent."""
    result = subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{_CHROMA_LABEL}"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise click.ClickException(result.stderr.strip() or "Chroma launchd agent is not loaded")
    console.print("[green]Chroma restarted[/]")


@chroma_command.command(name="status")
def chroma_status():
    """Show launchd and heartbeat status for the local Chroma server."""
    from .chroma_runtime import runtime_config, wait_for_chroma  # deferred: chromadb (#146)

    cfg = runtime_config()
    loaded = (
        subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{_CHROMA_LABEL}"],
            capture_output=True,
        ).returncode
        == 0
    )
    healthy = wait_for_chroma(cfg, timeout_s=0.5)
    console.print(f"launchd agent: {'[green]loaded[/]' if loaded else '[red]not loaded[/]'}")
    console.print(
        f"heartbeat: {'[green]healthy[/]' if healthy else '[red]unreachable[/]'} "
        f"at http://{cfg.host}:{cfg.port}"
    )
    if not loaded or not healthy:
        raise SystemExit(1)


@chroma_command.command(name="uninstall")
def chroma_uninstall():
    """Unload and remove the local Chroma launchd agent."""
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{_CHROMA_LABEL}"],
        check=False,
        capture_output=True,
    )
    if _CHROMA_PLIST.exists():
        _CHROMA_PLIST.unlink()
    console.print("[green]Chroma launchd agent removed[/]")


_HUB_LABEL = "com.ytk.hub"
_HUB_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{_HUB_LABEL}.plist"


def _hub_addr() -> tuple[str, int]:
    cfg = load_config()
    return cfg.hub.host, cfg.hub.port


@cli.group(name="ui", invoke_without_command=True)
@click.option("--host", default=None, help="Bind address (default: hub.host from config).")
@click.option("--port", default=None, type=int, help="Port (default: hub.port from config).")
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes (dev).")
@click.pass_context
def ui(ctx, host: str | None, port: int | None, reload: bool):
    """Run the hub in the foreground, or manage the background daemon."""
    if ctx.invoked_subcommand is not None:
        return
    from .chroma_runtime import runtime_config, wait_for_chroma  # deferred: chromadb (#146)

    chroma_cfg = runtime_config()
    if chroma_cfg.mode == "http" and not wait_for_chroma(chroma_cfg, timeout_s=30.0):
        raise click.ClickException(f"Chroma server unavailable at {chroma_cfg.url}")
    import uvicorn

    chost, cport = _hub_addr()
    host, port = host or chost, port or cport
    console.print(f"[bold cyan]ytk hub[/]  http://{host}:{port}")
    console.print("[dim]Ctrl-C to stop[/]")
    uvicorn.run(
        "ytk.ui.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="warning",
    )


@ui.command(name="install")
def ui_install():
    """Install the hub as an always-on launchd agent (KeepAlive, boots with you)."""
    ytk_bin = shutil.which("ytk")
    if not ytk_bin:
        console.print("[red]ytk binary not found in PATH.[/] Run [bold]uv tool install .[/] first.")
        raise SystemExit(1)
    host, port = _hub_addr()
    log_path = Path.home() / ".ytk" / "logs" / "hub.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _HUB_PLIST.parent.mkdir(parents=True, exist_ok=True)
    _HUB_PLIST.write_text(
        f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_HUB_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{ytk_bin}</string>
        <string>ui</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    subprocess.run(["launchctl", "unload", str(_HUB_PLIST)], check=False, capture_output=True)
    subprocess.run(["launchctl", "load", str(_HUB_PLIST)], check=True)
    console.print(f"[bold green]Installed:[/] {_HUB_PLIST}")
    console.print(f"Hub always on at [bold]http://{host}:{port}[/]  Logs: {log_path}")


@ui.command(name="uninstall")
def ui_uninstall():
    """Remove the hub launchd agent."""
    if not _HUB_PLIST.exists():
        console.print("[yellow]No hub plist found.[/] Nothing to uninstall.")
        return
    subprocess.run(["launchctl", "unload", str(_HUB_PLIST)], check=False)
    _HUB_PLIST.unlink()
    console.print(f"[bold green]Uninstalled:[/] {_HUB_PLIST}")


@ui.command(name="restart")
def ui_restart():
    """Restart the hub daemon (picks up code and config changes)."""
    r = subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{_HUB_LABEL}"],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        console.print(
            f"[red]kickstart failed:[/] {r.stderr.strip() or 'agent not loaded?'} "
            "Run [bold]ytk ui install[/] first."
        )
        raise SystemExit(1)
    host, port = _hub_addr()
    console.print(f"[bold green]Hub restarted[/] at http://{host}:{port}")


@ui.command(name="status")
def ui_status():
    """Show whether the hub daemon is loaded and responding."""
    import urllib.request

    host, port = _hub_addr()
    loaded = subprocess.run(["launchctl", "list", _HUB_LABEL], capture_output=True).returncode == 0
    console.print(f"launchd agent: {'[green]loaded[/]' if loaded else '[red]not loaded[/]'}")
    try:
        urllib.request.urlopen(f"http://{host}:{port}/api/tags", timeout=3)
        console.print(f"hub: [green]responding[/] at http://{host}:{port}")
    except Exception as exc:
        console.print(f"hub: [red]not responding[/] on port {port} ({exc})")


@cli.command(name="chat")
@click.argument("prompt", nargs=-1, required=False)
@click.option(
    "--print",
    "print_mode",
    is_flag=True,
    default=False,
    help="Non-interactive: print response and exit.",
)
def chat(prompt: tuple[str, ...], print_mode: bool):
    """Open a Claude Code session rooted in the ytk project directory.

    Conversations started here are attributed to ytk's memory, so vault
    queries and enrichment discussions don't pollute other project logs.

    With a PROMPT argument, passes it directly to claude (--print mode by
    default for one-shot queries; use --print explicitly for scripting).
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        console.print("[red]claude not found in PATH.[/] Install Claude Code first.")
        raise SystemExit(1)

    # Resolve ytk project root: two levels up from this file (ytk/cli.py)
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    args = [claude_bin]
    if prompt:
        prompt_text = " ".join(prompt)
        if print_mode:
            args += ["--print", prompt_text]
        else:
            args += ["--print", prompt_text]
    # exec replaces the current process — no subprocess overhead, signals propagate naturally
    os.execv(claude_bin, args)


@cli.group()
def visual():
    """SigLIP-2 visual embedding commands (issue #12)."""


@visual.command(name="index")
@click.option("--limit", type=int, default=None, help="Index only the first N covers (smoke test).")
def visual_index(limit: int | None):
    """Backfill the ytk_visual collection: one cover per save."""
    from .store import visual_count
    from .visual import index_covers

    console.print("[dim]Loading SigLIP-2 (first run downloads ~2.3GB)...[/dim]")
    done = index_covers(
        limit=limit,
        progress=lambda d, t: console.print(f"  [dim]{d}/{t}[/dim]"),
    )
    console.print(f"[green]Indexed {done} covers.[/] Collection size: {visual_count()}")


@visual.command(name="rebuild")
@click.option("--yes", is_flag=True, help="Confirm replacement of both visual collections.")
def visual_rebuild(yes: bool):
    """Replace and rebuild saved and pending visual indexes."""
    from .store import visual_index_enabled
    from .visual import rebuild_visual_indexes

    if not yes:
        raise click.ClickException("pass --yes to replace both visual collections")
    if not visual_index_enabled():
        raise click.ClickException("set YTK_VISUAL_INDEX=on before rebuilding")

    console.print("[dim]Rebuilding visual indexes from source covers...[/dim]")
    saved, pending = rebuild_visual_indexes(
        progress=lambda done, total: console.print(f"  [dim]{done}/{total}[/dim]"),
    )
    console.print(f"[green]Saved covers: {saved}[/]")
    console.print(f"[green]Pending covers: {pending}[/]")


@cli.command(name="similar")
@click.argument("query", nargs=-1, required=True)
@click.option(
    "--text",
    "is_text",
    is_flag=True,
    default=False,
    help="Treat QUERY as a text description instead of a save/image.",
)
@click.option("-n", type=int, default=8, help="Number of results.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Machine-readable output (for vtk and scripts).",
)
def similar(query: tuple[str, ...], is_text: bool, n: int, as_json: bool):
    """Visually similar saves for a save id, image path, URL, or --text description."""
    import json as _json

    from . import visual as vis
    from .store import get_visual_embedding, visual_similar

    q = " ".join(query)
    embedding = None
    item_id = None

    if is_text:
        embedding = vis.embed_text(q)
    elif get_visual_embedding(q) is not None:
        item_id = q
    elif Path(q).expanduser().exists():
        embedding = vis.embed_images([Path(q).expanduser()])[0]
    elif m := re.search(r"[?&]v=([\w-]{11})|youtu\.be/([\w-]{11})", q):
        item_id = f"yt:{m.group(1) or m.group(2)}"
    elif m := re.search(r"instagram\.com/(?:p|reel)/([\w-]+)", q):
        item_id = f"ig:{m.group(1)}"
    else:
        embedding = vis.embed_text(q)

    results = visual_similar(item_id=item_id, embedding=embedding, n=n)
    if as_json:
        click.echo(_json.dumps([r.__dict__ for r in results], indent=2))
        return
    if not results:
        console.print("[yellow]No matches — run `ytk visual index` first?[/]")
        return
    table = Table(box=box.SIMPLE)
    table.add_column("dist", justify="right")
    table.add_column("source")
    table.add_column("title / id")
    table.add_column("url", overflow="fold")
    for r in results:
        table.add_row(f"{r.distance:.3f}", r.source, r.title or r.item_id, r.url)
    console.print(table)


@cli.command(name="snap")
@click.argument("note", nargs=-1, required=False)
@click.option("--tags", default="", help="Comma-separated tags.")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True),
    default=None,
    help="Ingest this image file instead of the clipboard.",
)
@click.option(
    "--speak",
    is_flag=True,
    default=False,
    help="Record the note by voice (Enter to stop) instead of typing it.",
)
@click.option(
    "--note-audio",
    "note_audio",
    type=click.Path(exists=True),
    default=None,
    hidden=True,
    help="Background worker: transcribe this wav as the note.",
)
def snap(
    note: tuple[str, ...], tags: str, file_path: str | None, speak: bool, note_audio: str | None
):
    """Save the clipboard image (e.g. a Shottr screenshot) as a vault memory.

    Writes a lossless WebP + a note to second-brain/sources/screenshots/, indexes
    the text into ytk_memories and the image into ytk_visual.
    """
    import tempfile

    from .snap import save_snap

    if file_path:
        data = Path(file_path).read_bytes()
    else:
        if not shutil.which("pngpaste"):
            console.print("[red]pngpaste not found.[/] brew install pngpaste")
            raise SystemExit(1)
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            result = subprocess.run(["pngpaste", tmp.name], capture_output=True, text=True)
            data = Path(tmp.name).read_bytes() if result.returncode == 0 else b""
        if not data:
            console.print("[red]No image on the clipboard.[/]")
            raise SystemExit(1)

    text = " ".join(note).strip()
    if note_audio:
        from .memo import StageLog, ensure_wav
        from .memo import notify as memo_notify
        from .memo import transcribe as memo_transcribe

        slog = StageLog(datetime.now().strftime("%H%M%S"))
        cfg = load_config()
        try:
            text = memo_transcribe(ensure_wav(Path(note_audio)), cfg.whisper_model).strip()
            slog.mark("SNAP_TRANSCRIBED", f"{len(text)} chars")
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            note_path = save_snap(data, text, tag_list)
            slog.mark("SNAP_SAVED", note_path.name)
            snippet = text if len(text) <= 90 else text[:87] + "..."
            memo_notify(snippet or note_path.name, "snap saved", cfg.memo_notify or None)
        except Exception as exc:
            slog.mark("SNAP_FAILED", repr(exc))
            memo_notify(f"snap failed: {exc}", "failed", cfg.memo_notify or None)
            raise
        return
    if speak and not text:
        import tempfile as _tf

        from .memo import ensure_wav, record
        from .memo import transcribe as memo_transcribe

        cfg = load_config()
        with _tf.TemporaryDirectory() as td:
            from .memo import preload_model

            preload_model(cfg.whisper_model)
            console.print(
                "[bold red]\u25cf rec[/bold red]  [dim]speak your note, then press Enter[/dim]"
            )
            audio = record(Path(td) / "snap-note.wav", wait=lambda _prompt: input(""))
            with console.status(
                f"[cyan]transcribing[/] [dim]({cfg.whisper_model})[/dim]", spinner="dots"
            ):
                text = memo_transcribe(ensure_wav(audio), cfg.whisper_model).strip()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    note_path = save_snap(data, text, tag_list)
    console.print(f"[green]Saved[/] {note_path.name}")
    if speak:
        console.print(
            Panel(
                text or "[dim](empty transcript)[/dim]",
                title="[bold]transcript[/bold]",
                border_style="cyan",
                padding=(0, 1),
            )
        )
        time.sleep(4)


@cli.command(name="enrich-eval")
@click.option("--tone", required=True, help="Challenger tone preamble to test.")
def enrich_eval_cmd(tone):
    """Run the champion-vs-challenger enrichment eval and print the summary."""
    from .enrich_eval import run_eval

    r = run_eval(tone)
    click.echo(
        f"n={r['n']} winrate={r['winrate']:.2f} 95% CI [{r['ci'][0]:.2f}, {r['ci'][1]:.2f}] "
        f"faith_delta={r['faith_delta']:+.3f}"
    )
    click.echo("Smoke gate only (n small); not a ship decision.")
