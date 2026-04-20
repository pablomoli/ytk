"""YouTube Data API v3 playlist polling and ingestion pipeline for ytk."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import googleapiclient.discovery
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import Config
from .filter import check_post_enrichment, check_pre_transcript
from . import db


_YTK_DIR = Path.home() / ".ytk"
_CLIENT_SECRETS = _YTK_DIR / "client_secrets.json"
_TOKEN_FILE = _YTK_DIR / "token.json"
_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


@dataclass
class SyncResult:
    seen: int = 0
    already_processed: int = 0
    skipped: int = 0
    failed: int = 0
    ingested: int = 0

    @property
    def new(self) -> int:
        return self.seen - self.already_processed


def authenticate() -> googleapiclient.discovery.Resource:
    """
    Load or create OAuth credentials for the YouTube Data API v3.
    On first use this opens a browser-based consent flow and saves token.json.
    Subsequent calls reuse the cached token, refreshing it automatically if expired.
    Returns a googleapiclient Resource ready for API calls.
    """
    _YTK_DIR.mkdir(parents=True, exist_ok=True)

    creds: Credentials | None = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)

    if creds is None or not creds.valid:
        if creds is not None and creds.expired and creds.refresh_token:
            import google.auth.transport.requests as tr
            creds.refresh(tr.Request())
        else:
            if not _CLIENT_SECRETS.exists():
                raise FileNotFoundError(
                    f"Client secrets file not found: {_CLIENT_SECRETS}\n"
                    "Download it from the Google Cloud Console and place it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CLIENT_SECRETS), _SCOPES
            )
            flow.redirect_uri = "http://localhost"
            creds = flow.run_local_server(port=80, open_browser=False)

        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        _TOKEN_FILE.chmod(0o600)

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def fetch_playlist_videos(
    service: googleapiclient.discovery.Resource,
    playlist_name: str = "ytk",
) -> list[dict]:
    """
    Find the playlist named `playlist_name` among the authenticated user's playlists
    and return all its videos as a list of dicts: [{video_id, title, added_at}].
    Handles pagination for both the playlist list and the items list.
    Raises RuntimeError if no playlist with that name is found.
    """
    playlist_id = _find_playlist_id(service, playlist_name)

    videos: list[dict] = []
    page_token: str | None = None

    while True:
        kwargs: dict = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.playlistItems().list(**kwargs).execute()

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            resource = snippet.get("resourceId", {})
            video_id = resource.get("videoId", "")
            if not video_id:
                continue
            videos.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "added_at": snippet.get("publishedAt", ""),
                }
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return videos


def _find_playlist_id(
    service: googleapiclient.discovery.Resource, name: str
) -> str:
    """Search the user's playlists for one matching `name` (case-insensitive)."""
    page_token: str | None = None
    target = name.lower()

    while True:
        kwargs: dict = {
            "part": "snippet",
            "mine": True,
            "maxResults": 50,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.playlists().list(**kwargs).execute()

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            if snippet.get("title", "").lower() == target:
                return item["id"]

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    raise RuntimeError(
        f"No YouTube playlist named '{name}' found in your account."
    )


def sync(
    service: googleapiclient.discovery.Resource,
    cfg: Config,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> SyncResult:
    """
    Fetch the 'ytk' playlist, skip already-processed videos, and run the
    filter + enrichment + vault pipeline on each new video.

    All filter and pipeline failures are logged to stderr and recorded in the
    database — no exceptions propagate to the caller.

    If dry_run is True, print what would be processed without running the pipeline.
    Returns a SyncResult with counts: seen, already_processed, skipped, failed, ingested.
    """
    from .metadata import fetch_metadata
    from .transcript import fetch_transcript, segments_to_text
    from .enrich import enrich

    def _log(msg: str) -> None:
        if verbose:
            print(f"[ytk] {msg}", file=sys.stderr)

    result = SyncResult()
    _log("fetching playlist...")
    videos = fetch_playlist_videos(service)
    result.seen = len(videos)
    _log(f"playlist: {len(videos)} videos")

    for entry in videos:
        video_id: str = entry["video_id"]
        title: str = entry["title"]
        url = f"https://www.youtube.com/watch?v={video_id}"

        if db.is_processed(video_id):
            _log(f"skip (already processed): {title!r}")
            result.already_processed += 1
            continue

        if dry_run:
            print(f"[dry-run] would process: {title} ({video_id})", file=sys.stderr)
            continue

        _log(f"processing: {title!r}")
        try:
            _log(f"  metadata...")
            meta = fetch_metadata(url)
        except Exception as exc:
            reason = f"metadata fetch error: {exc}"
            print(f"[ytk] FAILED {title!r}: {reason}", file=sys.stderr)
            db.mark_failed(video_id, title, reason)
            result.failed += 1
            continue

        # Pre-transcript filter
        pre = check_pre_transcript(meta, cfg)
        if not pre.passed:
            reasons = "; ".join(f.detail for f in pre.failures)
            print(f"[ytk] SKIPPED {title!r}: {reasons}", file=sys.stderr)
            db.mark_skipped(video_id, title, reasons)
            result.skipped += 1
            continue

        _log(f"  transcript (model={cfg.whisper_model})...")
        try:
            segments, _source = fetch_transcript(url, whisper_model=cfg.whisper_model)
        except Exception as exc:
            reason = f"transcript fetch error: {exc}"
            print(f"[ytk] FAILED {title!r}: {reason}", file=sys.stderr)
            db.mark_failed(video_id, title, reason)
            result.failed += 1
            continue

        _log(f"  transcript: {len(segments)} segments via {_source!r}")
        _log(f"  enrichment...")
        try:
            enrichment = enrich(segments_to_text(segments), meta)
        except Exception as exc:
            reason = f"enrichment error: {exc}"
            print(f"[ytk] FAILED {title!r}: {reason}", file=sys.stderr)
            db.mark_failed(video_id, title, reason)
            result.failed += 1
            continue

        _log(f"  enrichment: tags={enrichment.interest_tags}")
        # Post-enrichment filter
        post = check_post_enrichment(enrichment, cfg)
        if not post.passed:
            reasons = "; ".join(f.detail for f in post.failures)
            print(f"[ytk] SKIPPED {title!r}: {reasons}", file=sys.stderr)
            db.mark_skipped(video_id, title, reasons)
            result.skipped += 1
            continue

        # Write vault note — import deferred so the module loads without vault.py.
        try:
            from .vault import NoteAlreadyExists, write_note  # type: ignore[import]
        except ImportError:
            NoteAlreadyExists = None  # type: ignore[assignment]
            write_note = None  # type: ignore[assignment]

        if write_note is None:
            reason = "vault.py not available"
            print(f"[ytk] FAILED {title!r}: {reason}", file=sys.stderr)
            db.mark_failed(video_id, title, reason)
            result.failed += 1
            continue

        _log(f"  writing vault note...")
        try:
            write_note(meta, enrichment, segments)
        except Exception as exc:
            if NoteAlreadyExists is not None and isinstance(exc, NoteAlreadyExists):
                print(f"[ytk] already in vault: {title!r}", file=sys.stderr)
                db.mark_processed(video_id, title)
                result.ingested += 1
                continue
            reason = f"vault write error: {exc}"
            print(f"[ytk] FAILED {title!r}: {reason}", file=sys.stderr)
            db.mark_failed(video_id, title, reason)
            result.failed += 1
            continue

        _log(f"  embedding...")
        try:
            from .store import upsert as _upsert
            _upsert(meta, enrichment, segments)
        except Exception as exc:
            print(f"[ytk] WARNING: embedding failed for {title!r}: {exc}", file=sys.stderr)

        db.mark_processed(video_id, title)
        print(f"[ytk] ingested: {title!r}", file=sys.stderr)
        result.ingested += 1

    return result
